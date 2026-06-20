"""
Downloads annual reports (40-F / 10-K) and company facts from SEC EDGAR.
Run: python -m backend.edgar
"""
import os
import json
import time
import requests
from bs4 import BeautifulSoup

from backend import config
from backend.companies import COMPANIES

ANNUAL_FORMS = ["40-F", "10-K"]  # skipping the /A amendments, they are mostly tiny part III updates
MIN_DOC_SIZE = 200_000  # anything smaller is certifications, consents etc
# exhibits that actually have the annual report content
# (EX-1/EX-2 is how RBC does it, EX-13 is the annual report for some 10-Ks)
# skipping EX-10 contracts, EX-21 subsidiaries, EX-97 clawback, EX-4 code of conduct...
KEEP_EXHIBITS = ["EX-99", "EX-1", "EX-2", "EX-13"]


def sec_get(url):
    # SEC wants a user agent with contact info + max 10 requests/sec
    if not config.EDGAR_USER_AGENT:
        raise Exception("EDGAR_USER_AGENT not set in .env")
    for attempt in range(4):
        time.sleep(0.15)
        r = requests.get(url, headers={"User-Agent": config.EDGAR_USER_AGENT}, timeout=60)
        if r.status_code == 200:
            return r
        if r.status_code in (429, 503):
            print("  rate limited, waiting...")
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
    raise Exception("failed to get " + url)


def list_annual_filings(cik):
    data = sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
    tables = [data["filings"]["recent"]]
    # banks file so much stuff that older 40-Fs fall out of "recent", need the extra pages
    for extra in data["filings"].get("files", []):
        tables.append(sec_get("https://data.sec.gov/submissions/" + extra["name"]).json())

    filings = []
    for t in tables:
        for i in range(len(t["form"])):
            if t["form"][i] in ANNUAL_FORMS:
                filings.append({
                    "form": t["form"][i],
                    "accession": t["accessionNumber"][i],
                    "filing_date": t["filingDate"][i],
                    "period_end": t["reportDate"][i],
                    "primary_doc": t["primaryDocument"][i],
                })
        # stop early once we have enough, no need to load 20 years of pages
        if len(filings) >= config.YEARS_TO_KEEP:
            break

    filings.sort(key=lambda f: f["period_end"], reverse=True)
    return filings


def filing_folder(cik, accession):
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"


def pick_documents(folder, filing):
    # the -index.htm page has a table: seq | description | document | type | size
    # for a 40-F the real content is in exhibits (AIF, MD&A, financial statements)
    # and the exhibit numbers are different for every company (EX-99.1 vs EX-1 vs EX-99.B3A)
    page = sec_get(f"{folder}/{filing['accession']}-index.htm").text
    soup = BeautifulSoup(page, "lxml")
    docs = []
    for row in soup.select("table.tableFile tr"):
        cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
        if len(cells) < 5:
            continue
        name = cells[2].split(" ")[0]
        # "EX-99.1" -> "EX-99", careful "EX-10.09" must not match "EX-1"
        exhibit = cells[3].upper().split(".")[0].strip()
        size = int(cells[4]) if cells[4].isdigit() else 0
        if not name.endswith(".htm"):
            continue
        if name == filing["primary_doc"]:
            docs.append(name)
        elif exhibit in KEEP_EXHIBITS and size >= MIN_DOC_SIZE:
            docs.append(name)
    return docs


def download_filing(company, filing):
    year = filing["period_end"][:4]
    out_dir = os.path.join(config.RAW_DIR, company["ticker"], year)
    meta_path = os.path.join(out_dir, "meta.json")
    if os.path.exists(meta_path):
        print(f"  {company['ticker']} {year} already downloaded")
        return

    folder = filing_folder(company["cik"], filing["accession"])
    docs = pick_documents(folder, filing)

    os.makedirs(out_dir, exist_ok=True)
    for name in docs:
        print(f"  downloading {company['ticker']} {year} {name}")
        html = sec_get(folder + "/" + name).content
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(html)

    meta = dict(filing)
    meta.update({
        "ticker": company["ticker"],
        "company": company["name"],
        "fiscal_year": int(year),
        "docs": [{"file": d, "url": folder + "/" + d} for d in docs],
    })
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)


def download_facts(company):
    os.makedirs(config.FACTS_DIR, exist_ok=True)
    data = sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company['cik']:010d}.json").json()
    with open(os.path.join(config.FACTS_DIR, company["ticker"] + ".json"), "w") as f:
        json.dump(data, f)


def run(tickers=None, known_accessions=None):
    """known_accessions = filings already in the db (the azure function passes these in,
    its /tmp folder is empty every run so it can't rely on local files)"""
    new_filings = []
    for company in COMPANIES:
        if tickers and company["ticker"] not in tickers:
            continue
        print(company["name"])
        filings = list_annual_filings(company["cik"])[: config.YEARS_TO_KEEP]
        got_new = False
        for filing in filings:
            if known_accessions is not None and filing["accession"] in known_accessions:
                continue
            year = filing["period_end"][:4]
            if not os.path.exists(os.path.join(config.RAW_DIR, company["ticker"], year, "meta.json")):
                new_filings.append((company["ticker"], year))
                got_new = True
            download_filing(company, filing)
        if got_new or known_accessions is None:
            download_facts(company)
    print("new filings:", new_filings)
    return new_filings


if __name__ == "__main__":
    run()
