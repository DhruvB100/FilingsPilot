# FilingsPilot - design doc

## What it is
A chat agent that answers questions about 10 Canadian companies that file annual reports with the SEC
(Cenovus, Suncor, TC Energy, Enbridge, CNQ, RBC, TD, BMO, CIBC, Shopify). Every answer has to cite a page
of a filing or a row of the financial data. If the sources don't have the answer it says so.

## Architecture

```
            SEC EDGAR (submissions, filing index, companyfacts)
                    |
     Azure Function (daily timer) / python -m backend.edgar
                    |
          raw html (Blob)  +  XBRL facts json
                    |                         \
   chunker (sections + pages)            load_facts (metric mapping)
                    |                           |
   embeddings (text-embedding-3-small, 512d)    |
                    v                           v
        PostgreSQL + pgvector:   chunks (vector + tsvector)    financials, companies
                    \___________________________/
                                 |
                LangGraph agent (gpt-5-mini on Azure OpenAI)
       plan -> agent <-> tools [search_filings, query_financials, calculate, flag_issue] -> finalize
                                 |                                     |
                FastAPI (SSE streaming) on Container Apps        Jira (flag_issue)
                 |               |               |
        React UI (SWA)    Cosmos DB (sessions)   OpenTelemetry -> App Insights (dashboard + alert)
                 |
        MCP server (Node/TS) calls the same /tools endpoints
```

## Data
- **Filings**: latest 2 annual reports per company (fiscal 2024 + 2025). For 40-F filers the content is in
  the exhibits (AIF, MD&A, financial statements), picked by exhibit type from the filing index page.
- **Chunks**: ~14k chunks, ~2000 chars max, never cross a page or section boundary. Pages come from the CSS
  page breaks in the html. Metadata: ticker, year, form, doc type, file, url, page, section.
- **Financials**: ~1,700 rows, 21 metrics mapped from ifrs-full and us-gaap tags. Fiscal year comes from the
  period end date (not the `fy` field, see issues log #3).

## Retrieval
Hybrid search: pgvector cosine top 40 + Postgres full text (OR of the query words, ts_rank_cd) top 40,
merged with reciprocal rank fusion (k=60), top 5 returned. Filters by ticker and year.

## Agent
- **plan** node: structured output (Pydantic `Plan`) with 2-5 steps. Shown in the UI as reasoning.
- **agent** node: gpt-5-mini with the 4 tools bound, low reasoning effort.
- **tools** node: LangGraph ToolNode.
- **finalize** node: citation check. Labels the model invented are removed, an answer with no real citation
  becomes a refusal.
- Limits: 6 tool rounds, 40k tokens per question, 1000 char questions.

## Guardrails
| Risk | Defense |
| --- | --- |
| Prompt injection in retrieved text | text wrapped in `<source>` tags, tags inside the text escaped, system prompt says it's data |
| Destructive / sneaky SQL | sqlglot parse: one statement, SELECT only, allowed tables only, blocked functions, auto LIMIT. Plus a read only db user with a 5s timeout |
| Made up numbers | calculate tool for all math, citation check in finalize |
| Jailbreaks | Azure content filter (handled as a refusal), off topic rule in prompt |
| Cost | token cap per request, max tool rounds, eval max-cost guard |
Tested by `evals/test_redteam.py` (15 attacks).

## Evaluation
50 question golden set (`evals/golden_set.json`): lookups, calculations, text questions with known pages,
hybrid questions, and questions it should refuse. Metrics: answer correctness (numeric match within 1%),
faithfulness (LLM judge), citation accuracy (right page or the financials table), recall@5 (search alone),
tool-call accuracy. CI runs a 10 question subset on PRs and fails if a metric drops more than 0.1.

## Deployment
Terraform (`infra/`): resource group, Postgres flexible server (B1ms), Cosmos DB serverless, storage,
Log Analytics + App Insights, Container Apps env + app (scale to zero), Function App (flex consumption),
storage static website for the UI, budget + error alert, workbook dashboard.

## Cost
Budget for the whole project is $5. See decision records 005 and 006, and the cost table in the README.
