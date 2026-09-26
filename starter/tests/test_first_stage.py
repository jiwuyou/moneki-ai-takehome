from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from kbqa.cleaning import build_clean_db, clean_rows, parse_date
from kbqa.policy_resolver import resolve_metric_policy
from kbqa.tools import DataTools


def test_current_metric_policy_is_selected():
    resolution = resolve_metric_policy(Path(__file__).parents[2] / "knowledge_base", date(2026, 9, 1))
    assert resolution.document.doc_id == "KB-001"
    assert resolution.document.status == "现行"
    assert resolution.document.effective_from == date(2026, 5, 1)


def test_date_formats_and_kb001_cleaning_order():
    assert parse_date("2026/6/7") == "2026-06-07"
    assert parse_date("07-06-2026") == "2026-06-07"
    assert parse_date("not-a-date") is None

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE sales (order_id, date, store_id, product_id, qty, amount, payment)")
    conn.executemany(
        "INSERT INTO sales VALUES (?,?,?,?,?,?,?)",
        [
            ("o1", "07-06-2026", " s01 ", "p1", "1", "¥10.00", " 微信 "),
            ("o1", "2026-06-07", "S01", "P2", "1", "12.00", "微信"),
            ("o1", "2026-06-07", "S01", "P2", "1", "12.00", "微信"),
            ("o2", "2026-06-07", "S99", "P1", "1", "10.00", "微信"),
            ("o3", "2026-06-07", "S01", "P1", "1", "", "微信"),
            ("o4", "2026-06-07", "S01", "P1", "0", "10.00", "微信"),
            ("o5", "bad", "S01", "P1", "1", "10.00", "微信"),
            ("o6", "2026-06-07", "S01", "P1", "1", "-10.00", "微信"),
        ],
    )
    rows, report = clean_rows(conn.execute("SELECT * FROM sales"), {"S01"}, {"P1", "P2"})
    assert len(rows) == 3
    assert report.kept_refund_rows == 1
    assert report.removed["1_unparseable_date"] == 1
    assert report.removed["2_empty_amount"] == 1
    assert report.removed["3_qty_le_zero"] == 1
    assert report.removed["4_store_not_in_stores"] == 1
    assert report.removed["6_duplicate_row"] == 1
    assert rows[0][1] == "2026-06-07"
    assert rows[0][2:4] == ("S01", "P1")


def test_real_dataset_metrics_match_public_contract(tmp_path):
    root = Path(__file__).parents[2]
    target = tmp_path / "clean.db"
    policy = resolve_metric_policy(root / "knowledge_base", date(2026, 9, 1))
    report = build_clean_db(root / "data" / "pos.db", target, policy.as_dict())
    assert report.kept_rows == 18290
    tools = DataTools(target)
    assert tools.query_metrics("2026-06-01", "2026-06-30") == {
        "start": "2026-06-01",
        "end": "2026-06-30",
        "store_id": None,
        "product_id": None,
        "net_revenue": 156757.0,
        "refund_amount": 953.0,
        "orders": 4311,
        "aov": 36.36,
        "qty": 6496,
    }
    assert tools.query_metrics("2026-09-01", "2026-09-30")["aov"] is None
    days = tools.daily_metrics("2026-06-08", "2026-06-12", "S03")["days"]
    assert days[-1] == {"date": "2026-06-12", "net_revenue": 998.0, "orders": 27, "aov": 36.96}
