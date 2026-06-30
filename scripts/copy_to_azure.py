"""
Copies the local postgres data (chunks with embeddings, financials, filings) into the azure database,
so nothing has to be embedded again.

python scripts/copy_to_azure.py "<azure DATABASE_URL from terraform output>" "<readonly password>"
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TABLES = {
    "chunks": "ticker, company, fiscal_year, form, doc_type, doc_file, doc_url, page, section, content, embedding",
    "financials": "ticker, metric, fiscal_year, period_end, value, unit, source_tag, form, accession",
    "filings": "ticker, fiscal_year, form, accession, filing_date, period_end",
}


def main(azure_url, readonly_password):
    from backend import config
    import psycopg

    local_url = config.DATABASE_URL
    # create the tables + read only user on azure first
    os.environ["READONLY_PASSWORD"] = readonly_password
    config.DATABASE_URL = azure_url
    from backend.db import create_tables
    create_tables()

    with psycopg.connect(local_url) as src, psycopg.connect(azure_url, autocommit=True) as dst:
        for table, cols in TABLES.items():
            if dst.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                print(table, "already has rows, skipping")
                continue
            # stream local COPY TO straight into azure COPY FROM
            with src.cursor().copy(f"COPY {table} ({cols}) TO STDOUT") as out, \
                    dst.cursor().copy(f"COPY {table} ({cols}) FROM STDIN") as inp:
                for data in out:
                    inp.write(data)
            print(table, dst.execute(f"SELECT count(*) FROM {table}").fetchone()[0], "rows")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
