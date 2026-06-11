"""
Small database snapshot for the CI eval job, so CI doesn't need the azure db or re-embedding.
Only the companies the CI questions use + all the financials.

python scripts/ci_fixture.py dump   -> evals/fixtures/ci_db.csv.gz files
python scripts/ci_fixture.py load   (used in github actions after the tables are created)
"""
import os
import sys
import gzip

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.db import get_conn, create_tables  # noqa: E402

CI_TICKERS = ["CVE", "SU", "RY", "SHOP"]
OUT = os.path.join(os.path.dirname(__file__), "..", "evals", "fixtures")
CHUNK_COLS = "ticker, company, fiscal_year, form, doc_type, doc_file, doc_url, page, section, content, embedding"
TABLES = {
    "chunks": (CHUNK_COLS, f"SELECT {CHUNK_COLS} FROM chunks WHERE ticker IN ({','.join(repr(t) for t in CI_TICKERS)}) ORDER BY id"),
    "financials": ("ticker, metric, fiscal_year, period_end, value, unit, source_tag, form, accession",
                   "SELECT ticker, metric, fiscal_year, period_end, value, unit, source_tag, form, accession FROM financials"),
    "filings": ("ticker, fiscal_year, form, accession, filing_date, period_end",
                "SELECT ticker, fiscal_year, form, accession, filing_date, period_end FROM filings"),
}


def dump():
    os.makedirs(OUT, exist_ok=True)
    conn = get_conn()
    for table, (_, query) in TABLES.items():
        path = os.path.join(OUT, f"{table}.csv.gz")
        with gzip.open(path, "wb") as f, conn.cursor().copy(f"COPY ({query}) TO STDOUT WITH CSV") as copy:
            for data in copy:
                f.write(data)
        print(table, os.path.getsize(path) // 1024, "KB")


def load():
    create_tables()
    conn = get_conn()
    for table, (cols, _) in TABLES.items():
        path = os.path.join(OUT, f"{table}.csv.gz")
        with gzip.open(path, "rb") as f, conn.cursor().copy(f"COPY {table} ({cols}) FROM STDIN WITH CSV") as copy:
            while block := f.read(1024 * 1024):
                copy.write(block)
        print("loaded", table, conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


if __name__ == "__main__":
    {"dump": dump, "load": load}[sys.argv[1]]()
