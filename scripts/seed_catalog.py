"""
Seed Mobile Clinic catalog: iPhone XR–16, Realme, Redmi, Samsung + accessories.
Safe to re-run (skips existing titles).

Usage:
  python scripts/seed_catalog.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from app import create_app
from app import db
from app.utils.helpers import generate_uuid


LOCATION = "Urlabari, Morang, Nepal"
DESC_PHONE = (
    "Verified second-hand unit from Mobile Clinic Urlabari. "
    "Checked battery health, display, cameras and ports. "
    "COD / QR available. Exchange options on selected listings."
)
DESC_ACC = (
    "Genuine-compatible accessory from Mobile Clinic Urlabari. "
    "Quality checked. COD / QR payment available."
)


def _phones():
    """(brand, model, variant, ram, storage, condition, price, featured)"""
    items = []

    # iPhone XR
    for storage, price in [("64GB", 28000), ("128GB", 32000)]:
        items.append(("Apple", "iPhone XR", storage, "3GB", storage, "Good", price, 0))

    # iPhone 11
    for storage, price in [("64GB", 35000), ("128GB", 39000), ("256GB", 45000)]:
        items.append(("Apple", "iPhone 11", storage, "4GB", storage, "Good", price, 0))

    # iPhone 11 Pro
    for storage, price in [("64GB", 42000), ("256GB", 52000)]:
        items.append(("Apple", "iPhone 11 Pro", storage, "4GB", storage, "Excellent", price, 1))

    # iPhone 11 Pro Max
    for storage, price in [("64GB", 48000), ("256GB", 58000)]:
        items.append(("Apple", "iPhone 11 Pro Max", storage, "4GB", storage, "Good", price, 1))

    # iPhone 12 series
    for model, base in [
        ("iPhone 12 mini", 42000),
        ("iPhone 12", 48000),
        ("iPhone 12 Pro", 58000),
        ("iPhone 12 Pro Max", 65000),
    ]:
        for storage, add in [("64GB", 0), ("128GB", 4000), ("256GB", 8000)]:
            if model in ("iPhone 12 Pro", "iPhone 12 Pro Max") and storage == "64GB":
                continue
            ram = "4GB" if "Pro" not in model else "6GB"
            items.append(("Apple", model, storage, ram, storage, "Excellent", base + add, 1 if "Pro" in model else 0))

    # iPhone 13 series
    for model, base in [
        ("iPhone 13 mini", 52000),
        ("iPhone 13", 58000),
        ("iPhone 13 Pro", 72000),
        ("iPhone 13 Pro Max", 80000),
    ]:
        for storage, add in [("128GB", 0), ("256GB", 7000), ("512GB", 14000)]:
            ram = "4GB" if "Pro" not in model else "6GB"
            items.append(("Apple", model, storage, ram, storage, "Like New", base + add, 1))

    # iPhone 14 series
    for model, base in [
        ("iPhone 14", 70000),
        ("iPhone 14 Plus", 78000),
        ("iPhone 14 Pro", 90000),
        ("iPhone 14 Pro Max", 98000),
    ]:
        for storage, add in [("128GB", 0), ("256GB", 8000), ("512GB", 16000)]:
            ram = "6GB"
            items.append(("Apple", model, storage, ram, storage, "Like New", base + add, 1))

    # iPhone 15 series
    for model, base in [
        ("iPhone 15", 95000),
        ("iPhone 15 Plus", 105000),
        ("iPhone 15 Pro", 125000),
        ("iPhone 15 Pro Max", 140000),
    ]:
        for storage, add in [("128GB", 0), ("256GB", 10000), ("512GB", 20000)]:
            ram = "6GB" if "Pro" not in model else "8GB"
            items.append(("Apple", model, storage, ram, storage, "Like New", base + add, 1))

    # iPhone 16 series
    for model, base in [
        ("iPhone 16", 120000),
        ("iPhone 16 Plus", 132000),
        ("iPhone 16 Pro", 155000),
        ("iPhone 16 Pro Max", 175000),
    ]:
        for storage, add in [("128GB", 0), ("256GB", 12000), ("512GB", 25000)]:
            ram = "8GB"
            items.append(("Apple", model, storage, ram, storage, "Brand New", base + add, 1))

    # Realme
    realme = [
        ("Realme", "C53", "6/128", "6GB", "128GB", "Good", 14500, 0),
        ("Realme", "C55", "8/256", "8GB", "256GB", "Good", 16500, 0),
        ("Realme", "C67", "8/128", "8GB", "128GB", "Excellent", 18500, 0),
        ("Realme", "Narzo 60", "8/128", "8GB", "128GB", "Good", 20000, 0),
        ("Realme", "Narzo 60 Pro", "8/256", "8GB", "256GB", "Excellent", 28000, 0),
        ("Realme", "11", "8/128", "8GB", "128GB", "Good", 22000, 0),
        ("Realme", "11 Pro", "8/256", "8GB", "256GB", "Excellent", 32000, 1),
        ("Realme", "12", "8/256", "8GB", "256GB", "Like New", 30000, 0),
        ("Realme", "12 Pro", "12/256", "12GB", "256GB", "Like New", 38000, 1),
        ("Realme", "12 Pro+", "12/256", "12GB", "256GB", "Like New", 45000, 1),
        ("Realme", "GT 6T", "8/256", "8GB", "256GB", "Like New", 42000, 1),
        ("Realme", "GT Neo 6", "12/256", "12GB", "256GB", "Excellent", 48000, 1),
        ("Realme", "Note 50", "4/128", "4GB", "128GB", "Good", 12000, 0),
        ("Realme", "C75", "8/256", "8GB", "256GB", "Brand New", 21000, 0),
    ]
    items.extend(realme)

    # Redmi / Xiaomi
    redmi = [
        ("Redmi", "13C", "6/128", "6GB", "128GB", "Good", 12500, 0),
        ("Redmi", "13", "8/256", "8GB", "256GB", "Excellent", 17500, 0),
        ("Redmi", "Note 12", "6/128", "6GB", "128GB", "Good", 18000, 0),
        ("Redmi", "Note 12 Pro", "8/256", "8GB", "256GB", "Excellent", 26000, 0),
        ("Redmi", "Note 13", "8/128", "8GB", "128GB", "Good", 22000, 0),
        ("Redmi", "Note 13 Pro", "8/256", "8GB", "256GB", "Excellent", 30000, 1),
        ("Redmi", "Note 13 Pro+", "12/256", "12GB", "256GB", "Like New", 38000, 1),
        ("Redmi", "Note 14", "8/256", "8GB", "256GB", "Like New", 28000, 0),
        ("Redmi", "Note 14 Pro", "8/256", "8GB", "256GB", "Like New", 35000, 1),
        ("Redmi", "14C", "4/128", "4GB", "128GB", "Good", 11000, 0),
        ("Redmi", "A3", "4/128", "4GB", "128GB", "Good", 9500, 0),
        ("Xiaomi", "14", "12/256", "12GB", "256GB", "Like New", 75000, 1),
        ("Xiaomi", "14T", "12/256", "12GB", "256GB", "Like New", 55000, 1),
        ("Xiaomi", "13T Pro", "12/256", "12GB", "256GB", "Excellent", 48000, 1),
        ("POCO", "X6 Pro", "12/256", "12GB", "256GB", "Excellent", 32000, 0),
        ("POCO", "M6 Pro", "8/256", "8GB", "256GB", "Good", 20000, 0),
        ("POCO", "F6", "12/256", "12GB", "256GB", "Like New", 42000, 1),
    ]
    items.extend(redmi)

    # Samsung
    samsung = [
        ("Samsung", "Galaxy A05", "4/64", "4GB", "64GB", "Good", 11000, 0),
        ("Samsung", "Galaxy A05s", "6/128", "6GB", "128GB", "Good", 14500, 0),
        ("Samsung", "Galaxy A15", "6/128", "6GB", "128GB", "Excellent", 18000, 0),
        ("Samsung", "Galaxy A25", "8/256", "8GB", "256GB", "Excellent", 26000, 0),
        ("Samsung", "Galaxy A35", "8/256", "8GB", "256GB", "Like New", 35000, 0),
        ("Samsung", "Galaxy A55", "8/256", "8GB", "256GB", "Like New", 45000, 1),
        ("Samsung", "Galaxy A54", "8/256", "8GB", "256GB", "Excellent", 38000, 0),
        ("Samsung", "Galaxy S21", "8/128", "8GB", "128GB", "Good", 42000, 0),
        ("Samsung", "Galaxy S21 FE", "8/256", "8GB", "256GB", "Excellent", 40000, 0),
        ("Samsung", "Galaxy S22", "8/128", "8GB", "128GB", "Excellent", 55000, 1),
        ("Samsung", "Galaxy S22 Ultra", "12/256", "12GB", "256GB", "Excellent", 75000, 1),
        ("Samsung", "Galaxy S23", "8/256", "8GB", "256GB", "Like New", 85000, 1),
        ("Samsung", "Galaxy S23 FE", "8/256", "8GB", "256GB", "Like New", 65000, 1),
        ("Samsung", "Galaxy S23 Ultra", "12/256", "12GB", "256GB", "Like New", 105000, 1),
        ("Samsung", "Galaxy S24", "8/256", "8GB", "256GB", "Brand New", 110000, 1),
        ("Samsung", "Galaxy S24+", "12/256", "12GB", "256GB", "Brand New", 125000, 1),
        ("Samsung", "Galaxy S24 Ultra", "12/256", "12GB", "256GB", "Brand New", 155000, 1),
        ("Samsung", "Galaxy S25", "12/256", "12GB", "256GB", "Brand New", 135000, 1),
        ("Samsung", "Galaxy S25 Ultra", "12/512", "12GB", "512GB", "Brand New", 175000, 1),
        ("Samsung", "Galaxy Z Flip5", "8/256", "8GB", "256GB", "Excellent", 90000, 1),
        ("Samsung", "Galaxy Z Fold5", "12/256", "12GB", "256GB", "Excellent", 140000, 1),
        ("Samsung", "Galaxy M14", "6/128", "6GB", "128GB", "Good", 15000, 0),
        ("Samsung", "Galaxy M34", "8/128", "8GB", "128GB", "Good", 22000, 0),
        ("Samsung", "Galaxy M35", "8/256", "8GB", "256GB", "Excellent", 28000, 0),
        ("Samsung", "Galaxy F15", "6/128", "6GB", "128GB", "Good", 17000, 0),
    ]
    items.extend(samsung)
    return items


def _accessories():
    """(title, brand, model, price, stock)"""
    return [
        ("Tempered Glass Universal", "Generic", "TG-UNI", 300, 50),
        ("Tempered Glass iPhone 11/XR", "Generic", "TG-IP11", 400, 30),
        ("Tempered Glass iPhone 12/13", "Generic", "TG-IP12", 450, 30),
        ("Tempered Glass iPhone 14/15", "Generic", "TG-IP14", 500, 30),
        ("Tempered Glass Samsung A series", "Generic", "TG-SA", 350, 40),
        ("Silicone Case iPhone 11", "Generic", "CASE-IP11", 500, 25),
        ("Silicone Case iPhone 12/13", "Generic", "CASE-IP12", 550, 25),
        ("Silicone Case iPhone 14/15", "Generic", "CASE-IP14", 600, 25),
        ("Silicone Case iPhone 16", "Generic", "CASE-IP16", 700, 20),
        ("Clear Case Samsung A15/A25", "Generic", "CASE-SA", 450, 25),
        ("Back Cover Redmi Note 13", "Generic", "CASE-RN13", 400, 20),
        ("Back Cover Realme 12", "Generic", "CASE-RM12", 400, 20),
        ("USB-C Fast Charger 25W", "Generic", "CHG-25W", 900, 40),
        ("USB-C Fast Charger 45W", "Generic", "CHG-45W", 1500, 20),
        ("Apple 20W USB-C Adapter (compatible)", "Generic", "CHG-20W", 1200, 25),
        ("Lightning Cable 1m", "Generic", "CBL-LTG", 500, 40),
        ("USB-C to USB-C Cable 1m", "Generic", "CBL-C2C", 450, 40),
        ("USB-C to Lightning Cable", "Generic", "CBL-C2L", 700, 30),
        ("Wireless Charger Pad 15W", "Generic", "WLS-15", 1800, 15),
        ("Power Bank 10000mAh", "Generic", "PB-10K", 1500, 20),
        ("Power Bank 20000mAh", "Generic", "PB-20K", 2500, 15),
        ("Bluetooth Earbuds TWS", "Generic", "TWS-01", 1800, 25),
        ("Neckband Earphones", "Generic", "NB-01", 1200, 20),
        ("Wired Earphones 3.5mm", "Generic", "WE-35", 400, 30),
        ("Phone Holder / Grip", "Generic", "HOLD-01", 350, 40),
        ("Car Mount Holder", "Generic", "CAR-01", 800, 15),
        ("Screen Cleaning Kit", "Generic", "CLN-01", 250, 30),
        ("OTG Adapter USB-C", "Generic", "OTG-C", 300, 25),
        ("SIM Ejector + Tool Kit", "Generic", "TOOL-01", 150, 40),
        ("Camera Lens Protector iPhone", "Generic", "LENS-IP", 400, 20),
        ("MagSafe-compatible Case iPhone 14/15", "Generic", "CASE-MAG", 1200, 15),
        ("Tablet / Phone Stand", "Generic", "STAND-01", 600, 15),
        ("Gaming Trigger Controller", "Generic", "GAME-01", 900, 10),
        ("Memory Card 64GB", "Generic", "SD-64", 800, 20),
        ("Memory Card 128GB", "Generic", "SD-128", 1200, 15),
        ("Phone Pouch Waterproof", "Generic", "POUCH-01", 500, 15),
        ("Ring Light Clip for Phone", "Generic", "RING-01", 700, 10),
        ("Selfie Stick Tripod", "Generic", "TRIP-01", 1100, 12),
        ("USB Fan Portable", "Generic", "FAN-01", 450, 10),
        ("Charging Dock Dual", "Generic", "DOCK-01", 1600, 8),
    ]


def insert_phone(brand, model, variant, ram, storage, condition, price, featured):
    title = f"{brand} {model} {variant}".strip()
    existing = db.fetch_one("SELECT id FROM products WHERE title = ?", (title,))
    if existing:
        return False
    cols_extra = ""
    vals_extra = ""
    params_extra = []
    # product_type if column exists
    try:
        db.fetch_value("SELECT product_type FROM products LIMIT 1")
        cols_extra = ", product_type"
        vals_extra = ", ?"
        params_extra = ["phone"]
    except Exception:
        pass

    sql = f"""
        INSERT INTO products (
            uuid, seller_id, is_admin_listing, title, brand, model, variant, ram, storage,
            condition, selling_price, is_negotiable, description, location, stock_quantity,
            payment_method, is_featured, is_active, is_hidden, warranty_status, accessories
            {cols_extra}
        ) VALUES (
            ?, NULL, 1, ?, ?, ?, ?, ?, ?,
            ?, ?, 1, ?, ?, 1,
            'both', ?, 1, 0, 'Seller warranty 7 days', 'Box/cable may vary'
            {vals_extra}
        )
    """
    params = [
        generate_uuid(),
        title,
        brand,
        model,
        variant,
        ram,
        storage,
        condition,
        float(price),
        DESC_PHONE,
        LOCATION,
        int(featured),
    ] + params_extra
    db.execute(sql, tuple(params))
    return True


def insert_accessory(title, brand, model, price, stock):
    full = f"{title}"
    existing = db.fetch_one("SELECT id FROM products WHERE title = ?", (full,))
    if existing:
        return False
    cols_extra = ""
    vals_extra = ""
    params_extra = []
    try:
        db.fetch_value("SELECT product_type FROM products LIMIT 1")
        cols_extra = ", product_type"
        vals_extra = ", ?"
        params_extra = ["accessory"]
    except Exception:
        pass

    sql = f"""
        INSERT INTO products (
            uuid, seller_id, is_admin_listing, title, brand, model, variant, ram, storage,
            condition, selling_price, is_negotiable, description, location, stock_quantity,
            payment_method, is_featured, is_active, is_hidden, warranty_status, accessories
            {cols_extra}
        ) VALUES (
            ?, NULL, 1, ?, ?, ?, '', '', '',
            'Brand New', ?, 0, ?, ?, ?,
            'both', 0, 1, 0, '7 days replacement', 'As shown'
            {vals_extra}
        )
    """
    params = [
        generate_uuid(),
        full,
        brand,
        model,
        float(price),
        DESC_ACC,
        LOCATION,
        int(stock),
    ] + params_extra
    db.execute(sql, tuple(params))
    return True


def main():
    app = create_app()
    with app.app_context():
        try:
            from app.db import init_schema

            init_schema()
        except Exception as e:
            print("Schema init warning:", e)

        added_p = 0
        skip_p = 0
        for row in _phones():
            if insert_phone(*row):
                added_p += 1
            else:
                skip_p += 1

        added_a = 0
        skip_a = 0
        for row in _accessories():
            if insert_accessory(*row):
                added_a += 1
            else:
                skip_a += 1

        print(f"Phones: +{added_p} new, {skip_p} already existed")
        print(f"Accessories: +{added_a} new, {skip_a} already existed")
        print("Done. Browse /phones and /phones/accessories")


if __name__ == "__main__":
    main()
