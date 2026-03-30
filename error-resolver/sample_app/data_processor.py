"""
Order Data Processor

Reads orders.csv, validates each row, calculates order totals,
and writes a summary report. Real errors encountered during processing
are logged automatically to Oracle APP_ERROR_LOGS.

Errors you will see in this data:
  - Missing customer name          (order 1003)
  - Missing quantity               (order 1004)
  - Invalid order date format      (order 1006)
  - Discount > 100%                (order 1007)
  - Missing customer ID            (order 1009)
  - Missing product name/price     (order 1010)
  - Zero quantity                  (order 1011)
  - Non-numeric quantity           (order 1013)
  - Negative unit price            (order 1015)
"""
import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

VALID_REGIONS = {"US-EAST", "US-WEST", "EU", "APAC"}
MAX_DISCOUNT_PCT = 100.0
CSV_PATH = os.path.join(os.path.dirname(__file__), "orders.csv")


@dataclass
class Order:
    order_id: str
    customer_id: str
    customer_name: str
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    order_date: datetime
    discount_pct: float
    region: str

    @property
    def subtotal(self) -> float:
        return self.quantity * self.unit_price

    @property
    def discount_amount(self) -> float:
        return self.subtotal * (self.discount_pct / 100.0)

    @property
    def total(self) -> float:
        return self.subtotal - self.discount_amount


@dataclass
class ProcessingResult:
    processed: list[Order] = field(default_factory=list)
    failed_rows: list[dict] = field(default_factory=list)

    @property
    def total_revenue(self) -> float:
        return sum(o.total for o in self.processed)

    @property
    def success_rate(self) -> float:
        total = len(self.processed) + len(self.failed_rows)
        return (len(self.processed) / total * 100) if total else 0


class OrderProcessor:
    """Validates and processes order rows from CSV."""

    def __init__(self, error_logger=None):
        self._error_logger = error_logger

    def _log(self, error: Exception, code: str, order_id: str):
        print(f"  [ERROR {code}] Order {order_id}: {error}")
        if self._error_logger:
            self._error_logger.log_error(
                error=error,
                error_code=code,
                module_name="OrderProcessor",
                user_id="data_pipeline",
                extra_context=f"order_id={order_id}",
            )

    def validate_row(self, row: dict) -> Order:
        """
        Validate a raw CSV row and return a typed Order object.
        Raises ValueError for any data quality issue.
        """
        order_id = row.get("order_id", "UNKNOWN").strip()

        # ── Required string fields ───────────────────────────────────
        customer_id = row.get("customer_id", "").strip()
        if not customer_id:
            raise ValueError(f"Missing customer_id for order {order_id}")

        customer_name = row.get("customer_name", "").strip()
        if not customer_name:
            raise ValueError(f"Missing customer_name for order {order_id}")

        product_name = row.get("product_name", "").strip()
        if not product_name:
            raise ValueError(f"Missing product_name for order {order_id}")

        # ── Numeric fields ───────────────────────────────────────────
        raw_qty = row.get("quantity", "").strip()
        if not raw_qty:
            raise ValueError(f"Missing quantity for order {order_id}")
        try:
            quantity = int(raw_qty)
        except ValueError:
            raise ValueError(
                f"Invalid quantity '{raw_qty}' for order {order_id} — must be an integer"
            )
        if quantity <= 0:
            raise ValueError(
                f"Quantity must be > 0, got {quantity} for order {order_id}"
            )

        raw_price = row.get("unit_price", "").strip()
        if not raw_price:
            raise ValueError(f"Missing unit_price for order {order_id}")
        try:
            unit_price = float(raw_price)
        except ValueError:
            raise ValueError(
                f"Invalid unit_price '{raw_price}' for order {order_id}"
            )
        if unit_price < 0:
            raise ValueError(
                f"unit_price cannot be negative, got {unit_price} for order {order_id}"
            )

        raw_discount = row.get("discount_pct", "0").strip()
        try:
            discount_pct = float(raw_discount)
        except ValueError:
            raise ValueError(
                f"Invalid discount_pct '{raw_discount}' for order {order_id}"
            )
        if discount_pct < 0 or discount_pct > MAX_DISCOUNT_PCT:
            raise ValueError(
                f"discount_pct must be 0–100, got {discount_pct} for order {order_id}"
            )

        # ── Date field ───────────────────────────────────────────────
        raw_date = row.get("order_date", "").strip()
        try:
            order_date = datetime.strptime(raw_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError(
                f"Invalid order_date '{raw_date}' for order {order_id} — expected YYYY-MM-DD"
            )

        # ── Region ───────────────────────────────────────────────────
        region = row.get("region", "").strip().upper()
        if region not in VALID_REGIONS:
            raise ValueError(
                f"Unknown region '{region}' for order {order_id} — valid: {VALID_REGIONS}"
            )

        return Order(
            order_id=order_id,
            customer_id=customer_id,
            customer_name=customer_name,
            product_id=row.get("product_id", "").strip(),
            product_name=product_name,
            quantity=quantity,
            unit_price=unit_price,
            order_date=order_date,
            discount_pct=discount_pct,
            region=region,
        )

    def process_csv(self, csv_path: str = CSV_PATH) -> ProcessingResult:
        result = ProcessingResult()

        print(f"\nProcessing: {csv_path}\n{'─' * 50}")

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                order_id = row.get("order_id", "?").strip()
                try:
                    order = self.validate_row(row)
                    result.processed.append(order)
                    print(f"  [OK] Order {order_id} — {order.customer_name} — ${order.total:,.2f}")
                except ValueError as e:
                    result.failed_rows.append({"order_id": order_id, "error": str(e)})
                    self._log(e, "VALIDATION-ERR", order_id)
                except Exception as e:
                    result.failed_rows.append({"order_id": order_id, "error": str(e)})
                    self._log(e, "UNEXPECTED-ERR", order_id)

        return result

    def print_summary(self, result: ProcessingResult):
        print(f"\n{'═' * 50}")
        print(f"  PROCESSING SUMMARY")
        print(f"{'═' * 50}")
        print(f"  Successful orders : {len(result.processed)}")
        print(f"  Failed orders     : {len(result.failed_rows)}")
        print(f"  Success rate      : {result.success_rate:.1f}%")
        print(f"  Total revenue     : ${result.total_revenue:,.2f}")

        if result.failed_rows:
            print(f"\n  Failed order IDs  : {[r['order_id'] for r in result.failed_rows]}")

        # Revenue by region
        by_region: dict[str, float] = {}
        for order in result.processed:
            by_region[order.region] = by_region.get(order.region, 0) + order.total
        if by_region:
            print(f"\n  Revenue by region:")
            for region, rev in sorted(by_region.items()):
                print(f"    {region:<10} ${rev:,.2f}")
        print(f"{'═' * 50}\n")
