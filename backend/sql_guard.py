"""
Guardrails for the text-to-sql tool (same idea as my DataLens project):
 - exactly one statement
 - SELECT only
 - only the financials / companies tables
 - no dangerous functions
 - always a LIMIT
The db user is also read only with a statement timeout, so this is the second layer not the only one.
"""
import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"financials", "companies"}
BLOCKED_FUNCTIONS = {"pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "lo_import", "lo_export",
                     "dblink", "set_config", "current_setting", "pg_terminate_backend", "pg_cancel_backend", "copy"}
MAX_ROWS = 200


class UnsafeSQL(Exception):
    pass


def check_sql(sql):
    """returns a cleaned sql string or raises UnsafeSQL"""
    if not sql or not sql.strip():
        raise UnsafeSQL("empty query")
    sql = sql.strip().rstrip(";").strip()

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except Exception as e:
        raise UnsafeSQL(f"could not parse sql: {e}")
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise UnsafeSQL("only one statement allowed")
    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise UnsafeSQL("only SELECT queries are allowed")

    # anything that writes, even nested in a CTE
    for bad in (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Merge, exp.TruncateTable):
        if tree.find(bad):
            raise UnsafeSQL("query contains a write operation")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names:
            continue
        if table.db and table.db.lower() != "public":
            raise UnsafeSQL(f"schema {table.db} not allowed")
        if name not in ALLOWED_TABLES:
            raise UnsafeSQL(f"table {name} not allowed, use financials or companies")

    for func in tree.find_all(exp.Func):
        name = (func.sql_name() if not isinstance(func, exp.Anonymous) else func.name).lower()
        if name in BLOCKED_FUNCTIONS:
            raise UnsafeSQL(f"function {name} not allowed")

    if isinstance(tree, exp.Select) and not tree.args.get("limit"):
        tree = tree.limit(MAX_ROWS)
    return tree.sql(dialect="postgres")
