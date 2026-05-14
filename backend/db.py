import os
import psycopg
from pgvector.psycopg import register_vector

from backend import config
from backend.companies import COMPANIES


def get_conn(url=None):
    conn = psycopg.connect(url or config.DATABASE_URL, autocommit=True)
    register_vector(conn)
    return conn


def create_tables():
    schema_path = os.path.join(os.path.dirname(__file__), "..", "sql", "schema.sql")
    with open(schema_path) as f:
        sql = f.read()
    # first connection without register_vector since the extension might not exist yet
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute(sql)
        for c in COMPANIES:
            conn.execute(
                "INSERT INTO companies (ticker, name, cik, sector) VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO NOTHING",
                (c["ticker"], c["name"], c["cik"], c["sector"]),
            )
    print("tables ready")


if __name__ == "__main__":
    create_tables()
