"""
Hybrid search = keyword (postgres full text) + vector (pgvector), merged with reciprocal rank fusion.
Run: python -m backend.search "cenovus capital spending 2025" CVE
"""
import re
import sys

from backend.db import get_conn
from backend.embeddings import embed_one

RRF_K = 60  # standard value from the RRF paper
CANDIDATES = 40

_conn = None


def conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = get_conn()
        # with WHERE ticker = ANY(...) postgres sometimes picks the hnsw index, which grabs the ef_search
        # nearest rows from ALL companies first and filters after -> only 24 of 40 results for 2 tickers.
        # iterative scan (pgvector 0.8) keeps scanning until it has enough rows that pass the filter
        _conn.execute("SET hnsw.iterative_scan = relaxed_order")
        _conn.execute("SET hnsw.ef_search = 100")
    return _conn


def build_filters(tickers, years):
    where, params = [], []
    if tickers:
        where.append("ticker = ANY(%s)")
        params.append([t.upper() for t in tickers])
    if years:
        where.append("fiscal_year = ANY(%s)")
        params.append([int(y) for y in years])
    return where, params


def vector_search(query, tickers=None, years=None, limit=CANDIDATES):
    where, params = build_filters(tickers, years)
    sql = "SELECT id FROM chunks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
    rows = conn().execute(sql, params + [embed_one(query), limit]).fetchall()
    return [r[0] for r in rows]


def keyword_search(query, tickers=None, years=None, limit=CANDIDATES):
    words = keywords(query)
    if not words:
        return []
    # first chunks that have ALL the words, then fill up with chunks that have ANY of them.
    # just OR-ing everything (first version) ranked long chunks full of "2025" and "ratio" on top
    ids = run_tsquery(" & ".join(words), tickers, years, limit)
    if len(ids) < limit:
        ids += [i for i in run_tsquery(" | ".join(words), tickers, years, limit) if i not in ids]
    return ids[:limit]


# company names match every chunk once we filter by ticker, and question words are just noise
SKIP_WORDS = {"cenovus", "suncor", "tc", "energy", "enbridge", "canadian", "natural", "resources", "cnq", "rbc", "royal",
              "bank", "td", "bmo", "montreal", "cibc", "shopify", "company", "what", "how", "much", "why", "did", "does",
              "was", "were", "when", "which", "and", "the", "its", "in", "of", "a", "to", "from", "for", "is", "it", "at",
              "as", "by", "end", "give", "say", "said", "reason"}


def keywords(query):
    words = re.sub(r"[^A-Za-z0-9 ]", " ", query.replace("'s", "")).lower().split()
    return [w for w in words if w not in SKIP_WORDS]


def run_tsquery(tsquery, tickers, years, limit):
    where, params = build_filters(tickers, years)
    where.append("tsv @@ to_tsquery('english', %s)")
    sql = f"""SELECT id FROM chunks WHERE {' AND '.join(where)}
              ORDER BY ts_rank_cd(tsv, to_tsquery('english', %s)) DESC LIMIT %s"""
    return [r[0] for r in conn().execute(sql, params + [tsquery, tsquery, limit]).fetchall()]


def hybrid_search(query, tickers=None, years=None, k=5):
    vec_ids = vector_search(query, tickers, years)
    kw_ids = keyword_search(query, tickers, years)

    scores = {}
    for rank, cid in enumerate(vec_ids):
        scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank + 1)
    for rank, cid in enumerate(kw_ids):
        scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank + 1)
    top = sorted(scores, key=scores.get, reverse=True)[:k]
    if not top:
        return []

    rows = conn().execute(
        """SELECT id, ticker, company, fiscal_year, form, doc_type, doc_file, doc_url, page, section, content
           FROM chunks WHERE id = ANY(%s)""",
        (top,),
    ).fetchall()
    cols = ["id", "ticker", "company", "fiscal_year", "form", "doc_type", "doc_file", "doc_url", "page", "section", "content"]
    by_id = {r[0]: dict(zip(cols, r)) for r in rows}
    results = []
    for cid in top:
        r = by_id[cid]
        r["score"] = round(scores[cid], 4)
        results.append(r)
    return results


if __name__ == "__main__":
    q = sys.argv[1]
    tickers = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    for r in hybrid_search(q, tickers):
        print(f"[{r['score']}] {r['ticker']} {r['fiscal_year']} {r['doc_type']} p.{r['page']} | {r['section']}")
        print("   ", r["content"][:250].replace("\n", " "))
