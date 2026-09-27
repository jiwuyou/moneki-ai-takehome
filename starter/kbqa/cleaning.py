"""把原始 sales 导进 var/clean.db，指标都查这张表。"""

from __future__ import annotations

import json
import sqlite3
from urllib.parse import quote
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Optional

#: 金额里的 `¥` 去掉再按数字解析。
_CURRENCY = str.maketrans("", "", "¥￥ \t　")

REMOVAL_REASONS = (
    "1_unparseable_date",
    "2_empty_amount",
    "3_qty_le_zero",
    "4_store_not_in_stores",
    "5_product_not_in_products",
    "6_duplicate_row",
)


def parse_amount(value: Optional[str]) -> tuple[Optional[int], str]:
    """返回 (分, 状态)。状态取值：`ok`、`empty`、`bad`。

    KB-001 §2.3 与 §3.2：`¥38.00` 与 `38.00` 是同一个金额；空金额直接剔除，**不回填**。
    """
    text = (value or "").translate(_CURRENCY).replace(",", "")
    if not text:
        return None, "empty"
    try:
        cents = int((Decimal(text) * 100).to_integral_value(rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None, "bad"
    return cents, "ok"


def parse_qty(value: Optional[str]) -> Optional[int]:
    """KB-001 §2.4：按整数解析。解析不了的按 0 处理，会被 §3.3 剔除。"""
    text = (value or "").strip()
    if not text:
        return None
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def parse_date(value: Optional[str]) -> Optional[str]:
    """Parse the three date formats allowed by KB-001 into ISO format."""
    text = (value or "").strip()
    if not text:
        return None
    formats = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None
@dataclass
class CleaningReport:
    raw_rows: int = 0
    kept_rows: int = 0
    kept_sales_rows: int = 0
    kept_refund_rows: int = 0
    removed: dict[str, int] = field(default_factory=lambda: {k: 0 for k in REMOVAL_REASONS})
    note_unparseable_amount: int = 0
    metric_policy: Optional[dict] = None
    cleaned_at: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "raw_rows": self.raw_rows,
            "removed": dict(self.removed, note_unparseable_amount=self.note_unparseable_amount),
            "kept_rows": self.kept_rows,
            "kept_sales_rows": self.kept_sales_rows,
            "kept_refund_rows": self.kept_refund_rows,
            "metric_policy": self.metric_policy,
            "cleaned_at": self.cleaned_at,
        }


def open_readonly(path: Path) -> sqlite3.Connection:
    """Open a SQLite database in read-only URI mode."""
    uri = "file:%s?mode=ro" % quote(path.resolve().as_posix(), safe="/")
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def clean_rows(
    rows: Iterable[sqlite3.Row],
    store_ids: Optional[set[str]] = None,
    product_ids: Optional[set[str]] = None,
) -> tuple[list[tuple], CleaningReport]:
    """Normalize and filter sales rows in the exact KB-001 order."""
    report = CleaningReport()
    kept: list[tuple] = []
    seen: set[tuple] = set()
    store_ids = {item.strip().upper() for item in (store_ids or set())}
    product_ids = {item.strip().upper() for item in (product_ids or set())}
    for row in rows:
        report.raw_rows += 1
        day = parse_date(row["date"])
        if day is None:
            report.removed["1_unparseable_date"] += 1
            continue
        cents, status = parse_amount(row["amount"])
        if status == "empty":
            report.removed["2_empty_amount"] += 1
            continue
        if status != "ok" or cents is None:
            report.note_unparseable_amount += 1
            report.removed["2_empty_amount"] += 1
            continue
        qty = parse_qty(row["qty"])
        if qty is None or qty <= 0:
            report.removed["3_qty_le_zero"] += 1
            continue
        order_id = (row["order_id"] or "").strip()
        store_id = (row["store_id"] or "").strip().upper()
        product_id = (row["product_id"] or "").strip().upper()
        payment = (row["payment"] or "").strip()
        if store_id not in store_ids:
            report.removed["4_store_not_in_stores"] += 1
            continue
        if product_id not in product_ids:
            report.removed["5_product_not_in_products"] += 1
            continue
        normalized = (order_id, day, store_id, product_id, qty, cents, payment)
        if normalized in seen:
            report.removed["6_duplicate_row"] += 1
            continue
        seen.add(normalized)
        kept.append((order_id, day, store_id, product_id, qty, cents, payment, int(cents < 0)))
    report.kept_rows = len(kept)
    report.kept_refund_rows = sum(1 for row in kept if row[-1])
    report.kept_sales_rows = report.kept_rows - report.kept_refund_rows
    return kept, report


_SCHEMA = """
CREATE TABLE stores (store_id TEXT PRIMARY KEY, store_name TEXT, category TEXT, district TEXT);
CREATE TABLE products (product_id TEXT PRIMARY KEY, product_name TEXT,
                       product_category TEXT, unit_price REAL);
CREATE TABLE sales_clean (
    order_id TEXT, date TEXT, store_id TEXT, product_id TEXT,
    qty INTEGER, amount_cents INTEGER, payment TEXT, is_refund INTEGER
);
CREATE INDEX idx_clean_date ON sales_clean(date);
CREATE INDEX idx_clean_store ON sales_clean(store_id);
CREATE INDEX idx_clean_product ON sales_clean(product_id);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


def build_clean_db(
    source: Path, target: Path, metric_policy: Optional[dict] = None
) -> CleaningReport:
    """从只读的源库重建清洗表。返回清洗台账，供 `/api/health` 与数据质量面板使用。"""
    if not source.exists():
        raise FileNotFoundError("找不到源数据库：%s" % source)
    src = open_readonly(source)
    try:
        stores = [
            (
                str(r[0]).strip().upper(),
                r[1],
                r[2],
                r[3],
            )
            for r in src.execute("SELECT store_id, store_name, category, district FROM stores")
        ]
        products = [
            (str(r[0]).strip().upper(), r[1], r[2], r[3])
            for r in src.execute(
                "SELECT product_id, product_name, product_category, unit_price FROM products"
            )
        ]
        rows, report = clean_rows(
            src.execute("SELECT order_id, date, store_id, product_id, qty, amount, payment FROM sales"),
            store_ids={row[0] for row in stores},
            product_ids={row[0] for row in products},
        )
    finally:
        src.close()

    report.metric_policy = metric_policy
    report.cleaned_at = datetime.now(timezone.utc).isoformat()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    out = sqlite3.connect(target)
    try:
        out.executescript(_SCHEMA)
        out.executemany("INSERT INTO stores VALUES (?,?,?,?)", stores)
        out.executemany("INSERT INTO products VALUES (?,?,?,?)", products)
        out.executemany("INSERT INTO sales_clean VALUES (?,?,?,?,?,?,?,?)", rows)
        out.execute(
            "INSERT INTO meta VALUES ('cleaning_report', ?)",
            (json.dumps(report.as_dict(), ensure_ascii=False),),
        )
        out.execute("INSERT INTO meta VALUES ('source_db', ?)", (source.name,))
        out.execute("INSERT INTO meta VALUES ('metric_policy', ?)", (json.dumps(metric_policy or {}, ensure_ascii=False),))
        out.execute("INSERT INTO meta VALUES ('cleaned_at', ?)", (report.cleaned_at,))
        out.commit()
    finally:
        out.close()
    return report
