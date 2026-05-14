"""
Embeds the chunks and loads them into postgres.
Run: python -m backend.index_filings          (all filings not indexed yet)
     python -m backend.index_filings SHOP 2025 (just one)
"""
import os
import sys
import glob
import json

from backend import config, embeddings
from backend.db import get_conn

BATCH = 50


def embed_text(c):
    # put company/year/section in front so the vector knows what the chunk is about
    return f"{c['company']} {c['fiscal_year']} {c['doc_type']} - {c['section']}\n{c['content']}"


def index_file(conn, path):
    with open(path, encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f]
    if not chunks:
        return
    ticker, year = chunks[0]["ticker"], chunks[0]["fiscal_year"]
    already = conn.execute("SELECT count(*) FROM chunks WHERE ticker=%s AND fiscal_year=%s", (ticker, year)).fetchone()[0]
    if already:
        print(f"{ticker} {year} already indexed ({already} chunks), skipping")
        return

    rows = []
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i + BATCH]
        vectors = embeddings.embed([embed_text(c)[:8000] for c in batch])
        for c, v in zip(batch, vectors):
            rows.append((c["ticker"], c["company"], c["fiscal_year"], c["form"], c["doc_type"],
                         c["doc_file"], c["doc_url"], c["page"], c["section"], c["content"], v))
        print(f"  {ticker} {year}: {min(i + BATCH, len(chunks))}/{len(chunks)}", end="\r")

    # insert everything at the end so a crash halfway doesn't leave half a filing in the db
    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO chunks (ticker, company, fiscal_year, form, doc_type, doc_file, doc_url, page, section, content, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                rows,
            )
    print(f"{ticker} {year}: {len(rows)} chunks indexed, total cost so far ${embeddings.cost_so_far():.4f}")


def record_filing(conn, ticker, year):
    meta_path = os.path.join(config.RAW_DIR, ticker, str(year), "meta.json")
    with open(meta_path) as f:
        m = json.load(f)
    conn.execute(
        """INSERT INTO filings (ticker, fiscal_year, form, accession, filing_date, period_end)
           VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (accession) DO NOTHING""",
        (ticker, year, m["form"], m["accession"], m["filing_date"], m["period_end"]),
    )


def run(ticker=None, year=None):
    conn = get_conn()
    pattern = f"{ticker}_{year}.jsonl" if ticker else "*.jsonl"
    for path in sorted(glob.glob(os.path.join(config.DATA_DIR, "chunks", pattern))):
        index_file(conn, path)
        t, y = os.path.basename(path).replace(".jsonl", "").split("_")
        record_filing(conn, t, int(y))
    print(f"done. embedding tokens used: {embeddings.tokens_used:,} (${embeddings.cost_so_far():.4f})")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        run(sys.argv[1].upper(), sys.argv[2])
    else:
        run()
