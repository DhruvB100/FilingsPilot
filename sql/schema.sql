CREATE EXTENSION IF NOT EXISTS vector;

-- text chunks from the filings, for RAG
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    company TEXT,
    fiscal_year INT,
    form TEXT,
    doc_type TEXT,
    doc_file TEXT,
    doc_url TEXT,
    page INT,
    section TEXT,
    content TEXT NOT NULL,
    embedding vector(512),
    -- keyword side of hybrid search
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(section, '') || ' ' || content)) STORED
);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_ticker_year_idx ON chunks (ticker, fiscal_year);

-- which filings are already indexed (used by the daily job)
CREATE TABLE IF NOT EXISTS filings (
    ticker TEXT,
    fiscal_year INT,
    form TEXT,
    accession TEXT PRIMARY KEY,
    filing_date DATE,
    period_end DATE,
    indexed_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS companies (
    ticker TEXT PRIMARY KEY,
    name TEXT,
    cik INT,
    sector TEXT
);

-- structured numbers from XBRL company facts
CREATE TABLE IF NOT EXISTS financials (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    metric TEXT NOT NULL,
    fiscal_year INT NOT NULL,
    period_end DATE,
    value NUMERIC,
    unit TEXT,
    source_tag TEXT,
    form TEXT,
    accession TEXT,
    UNIQUE (ticker, metric, fiscal_year)
);

-- read only user for the text-to-sql tool, can only SELECT the number tables
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agent_readonly') THEN
        CREATE ROLE agent_readonly LOGIN PASSWORD 'readonly';
    END IF;
END
$$;
GRANT CONNECT ON DATABASE filings TO agent_readonly;
GRANT USAGE ON SCHEMA public TO agent_readonly;
GRANT SELECT ON financials, companies TO agent_readonly;
ALTER ROLE agent_readonly SET statement_timeout = '5s';
ALTER ROLE agent_readonly SET default_transaction_read_only = on;
