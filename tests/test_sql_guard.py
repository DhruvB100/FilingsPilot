import pytest
from backend.sql_guard import check_sql, UnsafeSQL


def test_simple_select_gets_limit():
    sql = check_sql("SELECT ticker, value FROM financials WHERE metric = 'revenue'")
    assert "LIMIT 200" in sql


def test_join_with_companies_ok():
    check_sql("SELECT c.name, f.value FROM financials f JOIN companies c ON c.ticker = f.ticker")


def test_cte_ok():
    check_sql("WITH r AS (SELECT ticker, value FROM financials) SELECT * FROM r")


def test_semicolon_inside_string_is_fine():
    check_sql("SELECT * FROM financials WHERE ticker = 'x; drop table y'")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM financials; DROP TABLE financials",
    "DROP TABLE financials",
    "DELETE FROM financials",
    "UPDATE financials SET value = 0",
    "INSERT INTO financials (ticker) VALUES ('x')",
    "WITH x AS (DELETE FROM financials RETURNING *) SELECT * FROM x",
    "SELECT * FROM chunks",
    "SELECT * FROM pg_catalog.pg_shadow",
    "SELECT * FROM information_schema.tables",
    "SELECT pg_sleep(10)",
    "COPY financials TO STDOUT",
    "",
])
def test_blocked(sql):
    with pytest.raises(UnsafeSQL):
        check_sql(sql)
