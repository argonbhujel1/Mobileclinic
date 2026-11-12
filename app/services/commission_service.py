"""
Seller commission calculation and Pay Admin workflow.
"""
import logging
from datetime import datetime, timedelta
from app import db
from app.utils.helpers import generate_uuid, now_kathmandu, format_npr
from flask import current_app

logger = logging.getLogger(__name__)


def create_commission_for_sale(order_item_id: int, order_id: int, seller_id: int, sale_amount: float):
    """Create commission record after successful seller sale. 8% rate."""
    rate = current_app.config["COMMISSION_RATE"]
    amount = round(sale_amount * rate, 2)
    deadline_hours = current_app.config["COMMISSION_DEADLINE_HOURS"]
    deadline = (now_kathmandu() + timedelta(hours=deadline_hours)).isoformat()

    # Prevent duplicates
    existing = db.fetch_one(
        "SELECT id FROM seller_commissions WHERE order_item_id = ?",
        (order_item_id,),
    )
    if existing:
        return existing["id"]

    db.execute(
        """INSERT INTO seller_commissions
           (seller_id, order_item_id, order_id, sale_amount, commission_rate, commission_amount, status, deadline_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (seller_id, order_item_id, order_id, sale_amount, rate, amount, deadline),
    )
    commission_id = db.fetch_value("SELECT last_insert_rowid()")

    # Ledger debit
    balance = get_outstanding_balance(seller_id) + amount
    db.execute(
        """INSERT INTO commission_ledger (seller_id, commission_id, entry_type, amount, balance_after, description)
           VALUES (?, ?, 'debit', ?, ?, ?)""",
        (seller_id, commission_id, amount, balance, f"Commission on order item {order_item_id}"),
    )
    return commission_id


def get_outstanding_balance(seller_id: int) -> float:
    row = db.fetch_one(
        """SELECT COALESCE(SUM(commission_amount - paid_amount), 0) AS balance
           FROM seller_commissions
           WHERE seller_id = ? AND status IN ('pending', 'partial', 'overdue')""",
        (seller_id,),
    )
    return float(row["balance"]) if row else 0.0


def get_active_admin_qr() -> dict | None:
    return db.fetch_one(
        "SELECT * FROM admin_qr_codes WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
    )


def submit_commission_payment(seller_id: int, amount: float, transaction_ref: str, receipt_result: dict | None):
    outstanding = get_outstanding_balance(seller_id)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    # Allow partial by default; Admin can configure strict full-pay later
    uuid = generate_uuid()
    receipt_url = receipt_result["url"] if receipt_result else None
    receipt_pid = receipt_result["public_id"] if receipt_result else None

    db.execute(
        """INSERT INTO commission_payments
           (uuid, seller_id, amount, transaction_ref, receipt_url, receipt_public_id, status)
           VALUES (?, ?, ?, ?, ?, ?, 'pending_verification')""",
        (uuid, seller_id, amount, transaction_ref, receipt_url, receipt_pid),
    )
    return uuid


def verify_commission_payment(payment_id: int, admin_id: int, approve: bool, notes: str = ""):
    payment = db.fetch_one("SELECT * FROM commission_payments WHERE id = ?", (payment_id,))
    if not payment or payment["status"] != "pending_verification":
        raise ValueError("Invalid or already processed payment")

    if not approve:
        db.execute(
            "UPDATE commission_payments SET status = 'rejected', admin_notes = ?, verified_by = ?, verified_at = datetime('now') WHERE id = ?",
            (notes, admin_id, payment_id),
        )
        return

    # Apply payment to oldest pending commissions
    amount_left = float(payment["amount"])
    commissions = db.fetch_all(
        """SELECT * FROM seller_commissions
           WHERE seller_id = ? AND status IN ('pending', 'partial', 'overdue')
           ORDER BY created_at ASC""",
        (payment["seller_id"],),
    )
    for comm in commissions:
        if amount_left <= 0:
            break
        due = float(comm["commission_amount"]) - float(comm["paid_amount"])
        apply = min(amount_left, due)
        new_paid = float(comm["paid_amount"]) + apply
        new_status = "paid" if new_paid >= float(comm["commission_amount"]) - 0.01 else "partial"
        db.execute(
            "UPDATE seller_commissions SET paid_amount = ?, status = ?, updated_at = datetime('now') WHERE id = ?",
            (new_paid, new_status, comm["id"]),
        )
        amount_left -= apply

    balance = get_outstanding_balance(payment["seller_id"])
    db.execute(
        """INSERT INTO commission_ledger (seller_id, payment_id, entry_type, amount, balance_after, description)
           VALUES (?, ?, 'credit', ?, ?, ?)""",
        (payment["seller_id"], payment_id, payment["amount"], balance, "Commission payment verified"),
    )
    db.execute(
        "UPDATE commission_payments SET status = 'verified', admin_notes = ?, verified_by = ?, verified_at = datetime('now') WHERE id = ?",
        (notes, admin_id, payment_id),
    )
