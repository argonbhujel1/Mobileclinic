"""Auto-seed phones + accessories once when catalog is empty/low."""
from __future__ import annotations

import logging
from app import db
from app.utils.helpers import generate_uuid

log = logging.getLogger(__name__)

LOCATION = "Urlabari, Morang, Nepal"
DESC_PHONE = (
    "Verified second-hand unit from Mobile Clinic Urlabari. "
    "Checked battery, display, cameras and ports. COD / QR available."
)
DESC_ACC = (
    "Accessory from Mobile Clinic Urlabari. Quality checked. COD / QR available."
)

# Seed only if fewer than this many products
MIN_PRODUCTS = 20


def _phones():
    items = []
    for storage, price in [("64GB", 28000), ("128GB", 32000)]:
        items.append(("Apple", "iPhone XR", storage, "3GB", storage, "Good", price, 0))
    for storage, price in [("64GB", 35000), ("128GB", 39000), ("256GB", 45000)]:
        items.append(("Apple", "iPhone 11", storage, "4GB", storage, "Good", price, 0))
    for storage, price in [("64GB", 42000), ("256GB", 52000)]:
        items.append(("Apple", "iPhone 11 Pro", storage, "4GB", storage, "Excellent", price, 1))
    for storage, price in [("64GB", 48000), ("256GB", 58000)]:
        items.append(("Apple", "iPhone 11 Pro Max", storage, "4GB", storage, "Good", price, 1))

    for model, base in [
        ("iPhone 12 mini", 42000), ("iPhone 12", 48000),
        ("iPhone 12 Pro", 58000), ("iPhone 12 Pro Max", 65000),
    ]:
        for storage, add in [("64GB", 0), ("128GB", 4000), ("256GB", 8000)]:
            if "Pro" in model and storage == "64GB":
                continue
            ram = "6GB" if "Pro" in model else "4GB"
            items.append(("Apple", model, storage, ram, storage, "Excellent", base + add, 1 if "Pro" in model else 0))

    for model, base in [
        ("iPhone 13 mini", 52000), ("iPhone 13", 58000),
        ("iPhone 13 Pro", 72000), ("iPhone 13 Pro Max", 80000),
    ]:
        for storage, add in [("128GB", 0), ("256GB", 7000), ("512GB", 14000)]:
            ram = "6GB" if "Pro" in model else "4GB"
            items.append(("Apple", model, storage, ram, storage, "Like New", base + add, 1))

    for model, base in [
        ("iPhone 14", 70000), ("iPhone 14 Plus", 78000),
        ("iPhone 14 Pro", 90000), ("iPhone 14 Pro Max", 98000),
    ]:
        for storage, add in [("128GB", 0), ("256GB", 8000), ("512GB", 16000)]:
            items.append(("Apple", model, storage, "6GB", storage, "Like New", base + add, 1))

    for model, base in [
        ("iPhone 15", 95000), ("iPhone 15 Plus", 105000),
        ("iPhone 15 Pro", 125000), ("iPhone 15 Pro Max", 140000),
    ]:
        for storage, add in [("128GB", 0), ("256GB", 10000), ("512GB", 20000)]:
            ram = "8GB" if "Pro" in model else "6GB"
            items.append(("Apple", model, storage, ram, storage, "Like New", base + add, 1))

    for model, base in [
        ("iPhone 16", 120000), ("iPhone 16 Plus", 132000),
        ("iPhone 16 Pro", 155000), ("iPhone 16 Pro Max", 175000),
    ]:
        for storage, add in [("128GB", 0), ("256GB", 12000), ("512GB", 25000)]:
            items.append(("Apple", model, storage, "8GB", storage, "Brand New", base + add, 1))

    items += [
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
    return items


def _accessories():
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


def _has_product_type():
    try:
        db.fetch_value("SELECT product_type FROM products LIMIT 1")
        return True
    except Exception:
        return False


def _insert_phone(brand, model, variant, ram, storage, condition, price, featured, with_type):
    title = f"{brand} {model} {variant}".strip()
    if db.fetch_one("SELECT id FROM products WHERE title = ?", (title,)):
        return False
    if with_type:
        db.execute(
            """INSERT INTO products (
                uuid, seller_id, is_admin_listing, title, brand, model, variant, ram, storage,
                condition, selling_price, is_negotiable, description, location, stock_quantity,
                payment_method, is_featured, is_active, is_hidden, warranty_status, accessories, product_type
            ) VALUES (?, NULL, 1, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 1, 'both', ?, 1, 0, 'Seller warranty 7 days', 'Box/cable may vary', 'phone')""",
            (generate_uuid(), title, brand, model, variant, ram, storage, condition, float(price), DESC_PHONE, LOCATION, int(featured)),
        )
    else:
        db.execute(
            """INSERT INTO products (
                uuid, seller_id, is_admin_listing, title, brand, model, variant, ram, storage,
                condition, selling_price, is_negotiable, description, location, stock_quantity,
                payment_method, is_featured, is_active, is_hidden, warranty_status, accessories
            ) VALUES (?, NULL, 1, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 1, 'both', ?, 1, 0, 'Seller warranty 7 days', 'Box/cable may vary')""",
            (generate_uuid(), title, brand, model, variant, ram, storage, condition, float(price), DESC_PHONE, LOCATION, int(featured)),
        )
    return True


def _insert_acc(title, brand, model, price, stock, with_type):
    if db.fetch_one("SELECT id FROM products WHERE title = ?", (title,)):
        return False
    if with_type:
        db.execute(
            """INSERT INTO products (
                uuid, seller_id, is_admin_listing, title, brand, model, variant, ram, storage,
                condition, selling_price, is_negotiable, description, location, stock_quantity,
                payment_method, is_featured, is_active, is_hidden, warranty_status, accessories, product_type
            ) VALUES (?, NULL, 1, ?, ?, ?, '', '', '', 'Brand New', ?, 0, ?, ?, ?, 'both', 0, 1, 0, '7 days replacement', 'As shown', 'accessory')""",
            (generate_uuid(), title, brand, model, float(price), DESC_ACC, LOCATION, int(stock)),
        )
    else:
        db.execute(
            """INSERT INTO products (
                uuid, seller_id, is_admin_listing, title, brand, model, variant, ram, storage,
                condition, selling_price, is_negotiable, description, location, stock_quantity,
                payment_method, is_featured, is_active, is_hidden, warranty_status, accessories
            ) VALUES (?, NULL, 1, ?, ?, ?, '', '', '', 'Brand New', ?, 0, ?, ?, ?, 'both', 0, 1, 0, '7 days replacement', 'As shown')""",
            (generate_uuid(), title, brand, model, float(price), DESC_ACC, LOCATION, int(stock)),
        )
    return True


def ensure_catalog_seed():
    """Called from init_schema — fills catalog if nearly empty."""
    try:
        count = db.fetch_value("SELECT COUNT(*) FROM products") or 0
    except Exception as e:
        log.warning("Catalog seed skipped (count failed): %s", e)
        return

    import os
    force = os.getenv("CATALOG_FORCE_SEED", "").strip() in ("1", "true", "yes")
    if count >= MIN_PRODUCTS and not force:
        log.info("Catalog seed skip — already %s products", count)
        return

    with_type = _has_product_type()
    added = 0
    try:
        for row in _phones():
            if _insert_phone(*row, with_type=with_type):
                added += 1
        for row in _accessories():
            if _insert_acc(*row, with_type=with_type):
                added += 1
        log.info("Auto-seeded catalog: +%s products (was %s)", added, count)
    except Exception as e:
        log.warning("Catalog seed error: %s", e)
