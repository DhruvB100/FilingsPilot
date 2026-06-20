"""
Loads XBRL company facts into the financials table, one row per (company, metric, fiscal year).
Run: python -m backend.load_facts
"""
import os
import json
from datetime import date

from backend import config
from backend.companies import COMPANIES
from backend.db import get_conn

# our metric name -> xbrl tags to try in order (ifrs-full and us-gaap mixed, first one found wins)
# 7 companies report in IFRS, ENB / SHOP / TRP report in US GAAP
METRICS = {
    "revenue": ["Revenue", "Revenues", "RevenueFromContractsWithCustomers", "RevenueFromContractWithCustomerExcludingAssessedTax"],
    "net_income": ["ProfitLoss", "NetIncomeLoss"],
    "net_income_to_shareholders": ["ProfitLossAttributableToOwnersOfParent", "NetIncomeLoss"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "total_equity": ["Equity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"],
    "operating_cash_flow": ["CashFlowsFromUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
              "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
              "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "cash": ["CashAndCashEquivalents", "CashAndCashEquivalentsAtCarryingValue"],
    "eps_basic": ["BasicEarningsLossPerShare", "EarningsPerShareBasic"],
    "eps_diluted": ["DilutedEarningsLossPerShare", "EarningsPerShareDiluted"],
    "dividends_paid": ["DividendsPaidClassifiedAsFinancingActivities", "DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities",
                       "DividendsPaid", "PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "long_term_debt": ["LongtermBorrowings", "LongTermDebt", "LongTermDebtNoncurrent"],
    "income_tax": ["IncomeTaxExpenseContinuingOperations", "IncomeTaxExpenseBenefit"],
    "pretax_income": ["ProfitLossBeforeTax", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
    "interest_income": ["RevenueFromInterest"],
    "interest_expense": ["InterestExpense"],
    "depreciation": ["DepreciationAndAmortisationExpense", "DepreciationDepletionAndAmortization"],
    "operating_income": ["OperatingIncomeLoss"],
    "gross_profit": ["GrossProfit"],
    "rd_expense": ["ResearchAndDevelopmentExpense"],
}

ANNUAL_FORMS = ("10-K", "40-F", "10-K/A", "40-F/A")


def is_full_year(fact):
    # balance sheet items have no start date (point in time), those are fine
    if "start" not in fact:
        return True
    days = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
    return 350 <= days <= 380


def find_tag(facts, tag):
    for taxonomy in ("ifrs-full", "us-gaap"):
        if tag in facts.get(taxonomy, {}):
            return facts[taxonomy][tag]
    return None


def yearly_values(tag_data):
    """returns {fiscal_year: fact} using the period END date for the year, not the fy field
    (fy is the year of the filing, so the 2025 report's 2024 comparatives also say fy=2025)"""
    # pick the unit with the most values, some tags have CAD + USD versions
    unit = max(tag_data["units"], key=lambda u: len(tag_data["units"][u]))
    best = {}
    for fact in tag_data["units"][unit]:
        if fact.get("form") not in ANNUAL_FORMS or not is_full_year(fact):
            continue
        year = int(fact["end"][:4])
        # if the same year shows up in several filings keep the newest one (restatements)
        if year not in best or fact["filed"] > best[year]["filed"]:
            best[year] = fact
    return unit, best


def load_company(conn, company):
    path = os.path.join(config.FACTS_DIR, company["ticker"] + ".json")
    with open(path) as f:
        facts = json.load(f)["facts"]

    rows = 0
    for metric, tags in METRICS.items():
        done_years = set()
        for tag in tags:
            tag_data = find_tag(facts, tag)
            if not tag_data:
                continue
            unit, values = yearly_values(tag_data)
            for year, fact in values.items():
                if year in done_years:
                    continue
                done_years.add(year)
                conn.execute(
                    """INSERT INTO financials (ticker, metric, fiscal_year, period_end, value, unit, source_tag, form, accession)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (ticker, metric, fiscal_year) DO UPDATE
                       SET value = EXCLUDED.value, period_end = EXCLUDED.period_end, unit = EXCLUDED.unit,
                           source_tag = EXCLUDED.source_tag, form = EXCLUDED.form, accession = EXCLUDED.accession""",
                    (company["ticker"], metric, year, fact["end"], fact["val"], unit, tag, fact["form"], fact["accn"]),
                )
                rows += 1
    print(f"{company['ticker']}: {rows} rows")


def run():
    conn = get_conn()
    for company in COMPANIES:
        # the daily function only downloads facts for companies that had a new filing
        if os.path.exists(os.path.join(config.FACTS_DIR, company["ticker"] + ".json")):
            load_company(conn, company)


if __name__ == "__main__":
    run()
