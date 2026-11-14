"""The allow-list for exploratory SQL (GR-02), including its personal-data rules (GR-04).

Checks a parsed syntax tree, never the text. The caller executes the SQL
regenerated from the checked tree, so what runs is exactly what was checked
(ADR-007). The connection's own limits (GR-01) stay in place underneath.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from governed_analytics.manifest import MARTS_SCHEMA, Manifest

# Functions that read files, the network, the environment or run SQL strings.
BLOCKED_FUNCTIONS = {"query", "query_table", "getenv", "columns", "glob", "sniff_csv"}
BLOCKED_PREFIXES = ("read_", "parquet_", "csv_", "json_", "duckdb_", "pragma_", "sqlite_", "postgres_", "mysql_", "iceberg_", "delta_")


class SqlRejected(ValueError):
    """The SQL is outside the allow-list. The message says what to do instead."""

    def __init__(self, message: str, requirement: str = "GR-02"):
        super().__init__(message)
        self.requirement = requirement


@dataclass(frozen=True)
class CheckedSql:
    sql: str  # regenerated from the checked tree: this is what runs
    marts: tuple[str, ...]


def check(sql: str, manifest: Manifest) -> CheckedSql:
    try:
        statements = [s for s in sqlglot.parse(sql, dialect="duckdb") if s is not None]
    except ParseError as e:
        raise SqlRejected(f"Could not parse the SQL: {str(e).splitlines()[0]}. Write one DuckDB SELECT statement.") from None
    if len(statements) != 1:
        raise SqlRejected(f"Send exactly one statement; got {len(statements)}.")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise SqlRejected(f"Only SELECT queries are allowed, not {tree.key.upper()}.")
    if any(select.args.get("into") for select in tree.find_all(exp.Select)):
        raise SqlRejected("SELECT ... INTO creates a table and is not allowed. Remove the INTO clause.")

    marts = _check_tables(tree, manifest)
    _check_functions(tree)
    _check_personal_data(tree, manifest, marts)
    return CheckedSql(sql=tree.sql(dialect="duckdb"), marts=tuple(sorted(marts)))


def _check_tables(tree: exp.Expression, manifest: Manifest) -> set[str]:
    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    allowed = ", ".join(f"{MARTS_SCHEMA}.{m}" for m in sorted(manifest.columns))
    marts = set()
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise SqlRejected(f"Table functions such as {table.this.sql()} are not allowed. Read from: {allowed}.")
        name, schema = table.name.lower(), table.db.lower()
        if not schema and not table.catalog and name in ctes:
            continue
        if table.catalog or schema != MARTS_SCHEMA or name not in manifest.columns:
            raise SqlRejected(f"Only the marts can be queried: {table.sql()} is not one of {allowed}.")
        marts.add(name)
    return marts


def _check_functions(tree: exp.Expression) -> None:
    for function in tree.find_all(exp.Func):
        name = (function.name if isinstance(function, exp.Anonymous) else function.sql_name()).lower()
        if name in BLOCKED_FUNCTIONS or name.startswith(BLOCKED_PREFIXES):
            raise SqlRejected(f"The function {name}() is not allowed in exploratory SQL.")


def _check_personal_data(tree: exp.Expression, manifest: Manifest, marts: set[str]) -> None:
    pii = manifest.all_pii()
    for column in tree.find_all(exp.Column):
        if column.name.lower() in pii:
            raise SqlRejected(f"Column {column.name} is personal data and cannot be queried.", "GR-04")

    # DuckDB turns a bare table name or alias in a SELECT list into the whole row, PII included.
    row_names = {t.alias_or_name.lower() for t in tree.find_all(exp.Table)}
    for column in tree.find_all(exp.Column):
        if not column.table and column.name.lower() in row_names:
            raise SqlRejected(f"'{column.name}' refers to a whole row. Name the columns you need.", "GR-04")

    with_pii = sorted(m for m in marts if manifest.pii.get(m))
    for star in tree.find_all(exp.Star):
        if with_pii and not isinstance(star.parent, exp.Count):
            raise SqlRejected(
                f"SELECT * would include personal data from {', '.join(with_pii)}. Name the columns you need.",
                "GR-04",
            )
