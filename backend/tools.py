"""
The 4 agent tools. make_tools(sources) builds them for one request, every tool
adds what it found to `sources` so we can check the citations in the final answer.
"""
import os
import requests
import psycopg
from langchain_core.tools import tool

from backend import config
from backend.search import hybrid_search
from backend.sql_guard import check_sql, UnsafeSQL

MAX_CHUNK_CHARS = 1500

FINANCIALS_SCHEMA = """Tables (PostgreSQL):
financials(ticker TEXT, metric TEXT, fiscal_year INT, period_end DATE, value NUMERIC, unit TEXT, source_tag TEXT, form TEXT, accession TEXT)
companies(ticker TEXT, name TEXT, cik INT, sector TEXT)
tickers: CVE (Cenovus), SU (Suncor), TRP (TC Energy), ENB (Enbridge), CNQ (Canadian Natural), RY (RBC), TD, BMO, CM (CIBC), SHOP (Shopify)
metrics: revenue, net_income, net_income_to_shareholders, total_assets, total_liabilities, total_equity,
operating_cash_flow, capex, cash, eps_basic, eps_diluted, dividends_paid, long_term_debt, income_tax,
pretax_income, interest_income, interest_expense, depreciation, operating_income, gross_profit, rd_expense
values are in full units (not millions), unit is CAD or USD (or CAD/shares for eps).
Banks have fiscal years ending Oct 31, everyone else Dec 31. Not every metric exists for every company."""


def readonly_db_url():
    # same db but log in as the read only user
    return os.getenv("READONLY_DATABASE_URL") or config.DATABASE_URL.replace("filings:filings@", "agent_readonly:readonly@")


def clean_for_prompt(text):
    # stop retrieved text from closing our <source> tags and pretending to be something else
    return text.replace("<source", "&lt;source").replace("</source", "&lt;/source")


def make_tools(sources):
    """sources is a dict label -> info, filled while the agent runs"""

    @tool
    def search_filings(query: str, tickers: list[str] | None = None, years: list[int] | None = None) -> str:
        """Search the text of annual reports (40-F / 10-K, MD&A, AIF, financial statement notes).
        Use for explanations, reasons, strategy, risks, segment details, and numbers not in the financials table (like capex guidance).
        tickers: optional list like ["CVE", "SU"]. years: optional fiscal years like [2024, 2025].
        Returns sources labeled [S1], [S2]... that you must cite."""
        results = hybrid_search(query, tickers, years, k=5)
        if not results:
            return "No matching passages found."
        out = []
        for r in results:
            label = f"S{len([k for k in sources if k.startswith('S')]) + 1}"
            # same chunk found twice -> reuse the old label
            for k, v in sources.items():
                if v.get("chunk_id") == r["id"]:
                    label = k
            sources[label] = {
                "type": "filing", "chunk_id": r["id"], "ticker": r["ticker"], "company": r["company"],
                "fiscal_year": r["fiscal_year"], "doc_type": r["doc_type"], "doc_file": r["doc_file"], "page": r["page"],
                "section": r["section"], "url": r["doc_url"], "snippet": r["content"][:300],
            }
            out.append(
                f'<source id="{label}" company="{r["company"]}" fiscal_year="{r["fiscal_year"]}" '
                f'doc="{r["doc_type"]}" page="{r["page"]}" section="{r["section"]}">\n'
                f'{clean_for_prompt(r["content"][:MAX_CHUNK_CHARS])}\n</source>'
            )
        return "\n\n".join(out)

    @tool
    def query_financials(sql: str) -> str:
        """Run ONE read-only SQL SELECT on the structured financial data (from SEC XBRL company facts).
        Use for exact figures like revenue, net income, assets, eps across companies/years.
        """
        try:
            safe_sql = check_sql(sql)
        except UnsafeSQL as e:
            return f"Query rejected: {e}"
        try:
            with psycopg.connect(readonly_db_url()) as conn:
                cur = conn.execute(safe_sql)
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
        except Exception as e:
            return f"SQL error: {str(e)[:300]}"
        label = f"F{len([k for k in sources if k.startswith('F')]) + 1}"
        sources[label] = {"type": "financials", "sql": safe_sql, "rows": len(rows),
                          "note": "SEC XBRL company facts (financials table)"}
        if not rows:
            return f"[{label}] query returned no rows."
        lines = [" | ".join(cols)] + [" | ".join(str(v) for v in row) for row in rows[:50]]
        return f"[{label}] {len(rows)} rows\n" + "\n".join(lines)

    query_financials.description += "\n" + FINANCIALS_SCHEMA

    @tool
    def calculate(operation: str, a: float, b: float | None = None, years: float | None = None) -> str:
        """Do the math so you never calculate in your head.
        operation: one of
          growth_rate (percent change from a=old to b=new),
          cagr (compound annual growth from a=start to b=end over `years`),
          ratio (a / b), difference (b - a), percent_of (a as % of b), sum (a + b).
        """
        try:
            if operation == "growth_rate":
                result = (b - a) / abs(a) * 100
            elif operation == "cagr":
                result = ((b / a) ** (1 / years) - 1) * 100
            elif operation == "ratio":
                result = a / b
            elif operation == "difference":
                result = b - a
            elif operation == "percent_of":
                result = a / b * 100
            elif operation == "sum":
                result = a + b
            else:
                return f"unknown operation {operation}"
        except (TypeError, ZeroDivisionError) as e:
            return f"calculation error: {e}"
        return f"{operation}({a}, {b}{', years=' + str(years) if years else ''}) = {round(result, 4)}"

    @tool
    def flag_issue(summary: str, details: str, ticker: str) -> str:
        """Open a Jira ticket when you find a contradiction or anomaly between the report text and the
        structured numbers (e.g. text says revenue grew but the financials table shows a drop),
        or a data quality problem. Include the source labels in details."""
        if os.getenv("JIRA_DRY_RUN") == "1" or not os.getenv("JIRA_URL"):
            sources["JIRA"] = {"type": "jira", "key": "DRY-RUN", "summary": summary}
            return "Dry run: ticket not created (JIRA_DRY_RUN=1). Would have created: " + summary
        url = os.getenv("JIRA_URL").rstrip("/") + "/rest/api/3/issue"
        body = {
            "fields": {
                "project": {"key": os.getenv("JIRA_PROJECT_KEY", "FP")},
                "summary": f"[{ticker}] {summary}"[:250],
                "issuetype": {"name": "Bug"},
                "labels": ["filingspilot", "agent-flag"],
                # jira cloud v3 wants the description in their "ADF" json format
                "description": {
                    "type": "doc", "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": details[:5000]}]}],
                },
            }
        }
        r = requests.post(url, json=body, auth=(os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN")), timeout=20)
        if not r.ok:
            return f"Jira error {r.status_code}: {r.text[:200]}"
        key = r.json()["key"]
        sources["JIRA"] = {"type": "jira", "key": key, "summary": summary,
                           "url": os.getenv("JIRA_URL").rstrip("/") + "/browse/" + key}
        return f"Created Jira ticket {key}"

    return [search_filings, query_financials, calculate, flag_issue]
