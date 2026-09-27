from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from kbqa.service import Service
from kbqa.tools import validate_readonly_sql


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE sales_clean",
        "DELETE FROM sales_clean",
        "SELECT * FROM sqlite_master",
        "SELECT 1",
        "SELECT * FROM sales_clean; DELETE FROM sales_clean",
        "PRAGMA table_info(sales_clean)",
    ],
)
def test_rejects_write_or_metadata_sql(sql):
    with pytest.raises(ValueError):
        validate_readonly_sql(sql)


def test_readonly_sql_and_tool_parameters():
    service = Service()
    ok = service.run_tool("run_sql", {"sql": "SELECT COUNT(*) AS n FROM sales_clean"})
    assert ok["rows"][0]["n"] == 18290
    assert "error" in service.run_tool("run_sql", {"sql": "DELETE FROM sales_clean"})
    assert "error" in service.run_tool("query_metrics", {"start": "2026-07-31", "end": "2026-07-01"})
    assert "error" in service.run_tool("query_metrics", {"start": "2026-99-01", "end": "2026-09-01"})
    assert "error" in service.run_tool("top_products", {"start": "2026-06-01", "end": "2026-06-30", "limit": 1000})
    assert "error" in service.run_tool("does_not_exist", {})


def test_database_connection_is_read_only():
    service = Service()
    with pytest.raises(sqlite3.OperationalError):
        service.tools.conn.execute("DELETE FROM sales_clean")
