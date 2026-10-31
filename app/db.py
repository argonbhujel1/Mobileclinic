"""
Turso (libSQL) database access layer.
Uses libsql-client for remote connectivity.
"""
import os
import json
import logging
from contextlib import contextmanager
from typing import Any, Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)

_client = None


def _clean_env(val: str) -> str:
    val = (val or "").strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        val = val[1:-1].strip()
    return val


def _local_sqlite_client():
    import libsql_client
    path = os.getenv("LOCAL_SQLITE_PATH", "mobile_clinic.db")
    if not path.startswith("file:"):
        path = "file:" + path
    client = libsql_client.create_client_sync(path)
    logger.warning("Using local SQLite: %s", path)
    return client


def get_client():
    """Lazy-init Turso client (or local SQLite on missing/invalid credentials)."""
    global _client
    if _client is not None:
        return _client

    force_local = (os.getenv("USE_LOCAL_DB") or "").strip().lower() in ("1", "true", "yes")
    url = _clean_env(os.getenv("TURSO_DATABASE_URL", ""))
    token = _clean_env(os.getenv("TURSO_AUTH_TOKEN", ""))

    if force_local or not url:
        _client = _local_sqlite_client()
        return _client

    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
        logger.info("Converted TURSO_DATABASE_URL libsql:// → https://")

    if not token:
        logger.error("TURSO_AUTH_TOKEN is empty — falling back to local SQLite")
        _client = _local_sqlite_client()
        return _client

    try:
        import libsql_client
        client = libsql_client.create_client_sync(url=url, auth_token=token)
        # Probe auth immediately
        try:
            client.execute("SELECT 1")
        except Exception as probe_err:
            err_s = str(probe_err)
            if "401" in err_s or "Unauthorized" in err_s or "auth" in err_s.lower():
                logger.error(
                    "Turso auth failed (401). Token invalid/expired. "
                    "Regenerate token in Turso dashboard, or set USE_LOCAL_DB=true. Falling back to local SQLite. Error: %s",
                    probe_err,
                )
                _client = _local_sqlite_client()
                return _client
            raise
        _client = client
        logger.info("Connected to Turso database")
        return _client
    except Exception as e:
        logger.error("Failed to connect to Turso: %s — trying local SQLite", e)
        try:
            _client = _local_sqlite_client()
            return _client
        except Exception as e2:
            logger.error("Local SQLite also failed: %s", e2)
            raise


def last_insert_id() -> Optional[int]:
    """Reliable last insert id (Turso + local)."""
    val = fetch_value("SELECT last_insert_rowid()")
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def execute(sql: str, params: Optional[Tuple] = None) -> Any:
    """Execute a statement and return result."""
    client = get_client()
    if params:
        return client.execute(sql, params)
    return client.execute(sql)


def execute_many(sql: str, params_list: List[Tuple]) -> None:
    """Execute many statements."""
    client = get_client()
    for params in params_list:
        client.execute(sql, params)


def fetch_one(sql: str, params: Optional[Tuple] = None) -> Optional[Dict]:
    """Fetch a single row as dict."""
    result = execute(sql, params)
    if not result.rows:
        return None
    columns = [col[0] if isinstance(col, tuple) else col for col in result.columns]
    row = result.rows[0]
    return dict(zip(columns, row))


def fetch_all(sql: str, params: Optional[Tuple] = None) -> List[Dict]:
    """Fetch all rows as list of dicts."""
    result = execute(sql, params)
    if not result.rows:
        return []
    columns = [col[0] if isinstance(col, tuple) else col for col in result.columns]
    return [dict(zip(columns, row)) for row in result.rows]


def fetch_value(sql: str, params: Optional[Tuple] = None) -> Any:
    """Fetch a single scalar value."""
    result = execute(sql, params)
    if not result.rows or not result.rows[0]:
        return None
    return result.rows[0][0]


@contextmanager
def transaction():
    """Simple transaction context (libSQL supports batch)."""
    client = get_client()
    try:
        yield client
        # libsql-client auto-commits; for explicit control use batch
    except Exception:
        raise


def init_schema():
    """Create all tables if they do not exist."""
    schema_sql = """
    -- Users
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        mobile TEXT,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'customer' CHECK(role IN ('admin','customer','seller','staff')),
        is_active INTEGER NOT NULL DEFAULT 0,
        is_verified INTEGER NOT NULL DEFAULT 0,
        must_change_password INTEGER NOT NULL DEFAULT 0,
        profile_photo_url TEXT,
        profile_photo_public_id TEXT,
        seller_username TEXT UNIQUE,
        address TEXT,
        latitude REAL,
        longitude REAL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_login_at TEXT,
        restricted INTEGER NOT NULL DEFAULT 0,
        restriction_reason TEXT
    );

    CREATE TABLE IF NOT EXISTS email_verifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        otp_hash TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        expires_at TEXT NOT NULL,
        verified_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS seller_applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        full_name TEXT NOT NULL,
        mobile TEXT NOT NULL,
        email TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
        requested_username TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        processed_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS seller_credential_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        password_plain_temp TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sent','failed')),
        scheduled_at TEXT NOT NULL,
        processed_at TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (application_id) REFERENCES seller_applications(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT UNIQUE NOT NULL,
        seller_id INTEGER,
        is_admin_listing INTEGER NOT NULL DEFAULT 0,
        title TEXT NOT NULL,
        brand TEXT NOT NULL,
        model TEXT NOT NULL,
        variant TEXT,
        ram TEXT,
        storage TEXT,
        condition TEXT NOT NULL,
        selling_price REAL NOT NULL,
        is_negotiable INTEGER NOT NULL DEFAULT 0,
        description TEXT NOT NULL,
        imei_serial TEXT,
        category_id INTEGER,
        warranty_status TEXT,
        warranty_details TEXT,
        accessories TEXT,
        location TEXT,
        stock_quantity INTEGER NOT NULL DEFAULT 1,
        payment_method TEXT NOT NULL DEFAULT 'both' CHECK(payment_method IN ('cod','qr','both')),
        qr_code_url TEXT,
        qr_code_public_id TEXT,
        is_featured INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        is_hidden INTEGER NOT NULL DEFAULT 0,
        views_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (seller_id) REFERENCES users(id),
        FOREIGN KEY (category_id) REFERENCES categories(id)
    );

    CREATE TABLE IF NOT EXISTS product_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        cloudinary_url TEXT NOT NULL,
        cloudinary_public_id TEXT NOT NULL,
        display_order INTEGER NOT NULL DEFAULT 0,
        is_primary INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT UNIQUE NOT NULL,
        user_id INTEGER,
        guest_name TEXT,
        guest_email TEXT,
        guest_mobile TEXT,
        delivery_address TEXT NOT NULL,
        delivery_latitude REAL,
        delivery_longitude REAL,
        payment_method TEXT NOT NULL,
        payment_status TEXT NOT NULL DEFAULT 'pending' CHECK(payment_status IN ('pending','awaiting_verification','paid','failed','refunded','cod')),
        payment_reference TEXT,
        payment_qr_snapshot TEXT,
        total_amount REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','confirmed','processing','shipped','delivered','cancelled','refunded')),
        tracking_token TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        product_title TEXT NOT NULL,
        product_price REAL NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        is_admin_listing INTEGER NOT NULL DEFAULT 0,
        seller_id INTEGER,
        commission_rate REAL DEFAULT 0,
        commission_amount REAL DEFAULT 0,
        FOREIGN KEY (order_id) REFERENCES orders(id),
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (seller_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT UNIQUE NOT NULL,
        order_id INTEGER,
        user_id INTEGER,
        amount REAL NOT NULL,
        method TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        reference_id TEXT,
        receipt_url TEXT,
        receipt_public_id TEXT,
        notes TEXT,
        verified_by INTEGER,
        verified_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (order_id) REFERENCES orders(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS payment_proofs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payment_id INTEGER,
        commission_payment_id INTEGER,
        uploader_id INTEGER,
        cloudinary_url TEXT NOT NULL,
        cloudinary_public_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (payment_id) REFERENCES payments(id),
        FOREIGN KEY (uploader_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS seller_commissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        order_item_id INTEGER NOT NULL,
        order_id INTEGER NOT NULL,
        sale_amount REAL NOT NULL,
        commission_rate REAL NOT NULL,
        commission_amount REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','partial','paid','overdue','waived')),
        deadline_at TEXT,
        paid_amount REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (seller_id) REFERENCES users(id),
        FOREIGN KEY (order_item_id) REFERENCES order_items(id),
        FOREIGN KEY (order_id) REFERENCES orders(id)
    );

    CREATE TABLE IF NOT EXISTS commission_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT UNIQUE NOT NULL,
        seller_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        transaction_ref TEXT,
        receipt_url TEXT,
        receipt_public_id TEXT,
        status TEXT NOT NULL DEFAULT 'pending_verification' CHECK(status IN ('pending_verification','verified','rejected')),
        admin_notes TEXT,
        verified_by INTEGER,
        verified_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (seller_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS commission_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        commission_id INTEGER,
        payment_id INTEGER,
        entry_type TEXT NOT NULL CHECK(entry_type IN ('debit','credit','adjustment')),
        amount REAL NOT NULL,
        balance_after REAL NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (seller_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS repair_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id TEXT UNIQUE NOT NULL,
        user_id INTEGER,
        guest_name TEXT,
        guest_email TEXT,
        guest_mobile TEXT,
        phone_brand TEXT NOT NULL,
        phone_model TEXT NOT NULL,
        problem_description TEXT NOT NULL,
        pickup_address TEXT NOT NULL,
        pickup_latitude REAL,
        pickup_longitude REAL,
        pickup_instructions TEXT,
        status TEXT NOT NULL DEFAULT 'submitted' CHECK(status IN (
            'submitted','accepted','staff_assigned','pickup_started','phone_collected',
            'arrived_at_shop','diagnosis','awaiting_approval','repair_in_progress',
            'repair_completed','delivery_assigned','delivery_started','delivered','completed','cancelled','declined'
        )),
        assigned_staff_id INTEGER,
        estimate_amount REAL,
        estimate_notes TEXT,
        customer_approved INTEGER,
        tracking_token TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (assigned_staff_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS repair_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repair_ticket_id INTEGER NOT NULL,
        cloudinary_url TEXT NOT NULL,
        cloudinary_public_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (repair_ticket_id) REFERENCES repair_tickets(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS repair_estimates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repair_ticket_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        notes TEXT,
        created_by INTEGER,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (repair_ticket_id) REFERENCES repair_tickets(id)
    );

    CREATE TABLE IF NOT EXISTS repair_status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repair_ticket_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        notes TEXT,
        changed_by INTEGER,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (repair_ticket_id) REFERENCES repair_tickets(id)
    );

    CREATE TABLE IF NOT EXISTS trips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT UNIQUE NOT NULL,
        repair_ticket_id INTEGER NOT NULL,
        staff_id INTEGER NOT NULL,
        trip_type TEXT NOT NULL CHECK(trip_type IN ('pickup','delivery')),
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','started','in_progress','completed','cancelled')),
        destination_lat REAL,
        destination_lng REAL,
        destination_address TEXT,
        started_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (repair_ticket_id) REFERENCES repair_tickets(id),
        FOREIGN KEY (staff_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS trip_location_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_id INTEGER NOT NULL,
        staff_id INTEGER NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        accuracy REAL,
        recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (trip_id) REFERENCES trips(id),
        FOREIGN KEY (staff_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS staff_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repair_ticket_id INTEGER NOT NULL,
        staff_id INTEGER NOT NULL,
        role TEXT DEFAULT 'pickup_delivery',
        assigned_by INTEGER,
        assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (repair_ticket_id) REFERENCES repair_tickets(id),
        FOREIGN KEY (staff_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS exchange_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT UNIQUE NOT NULL,
        customer_id INTEGER,
        guest_name TEXT,
        guest_email TEXT,
        guest_mobile TEXT,
        offered_phone_details TEXT NOT NULL,
        desired_product_id INTEGER,
        cash_difference REAL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','rejected','completed','cancelled')),
        admin_notes TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (customer_id) REFERENCES users(id),
        FOREIGN KEY (desired_product_id) REFERENCES products(id)
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        link TEXT,
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS email_delivery_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        template_name TEXT,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sent','failed')),
        error_message TEXT,
        related_type TEXT,
        related_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        sent_at TEXT
    );

    CREATE TABLE IF NOT EXISTS website_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        setting_key TEXT UNIQUE NOT NULL,
        setting_value TEXT,
        setting_type TEXT DEFAULT 'string',
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_by INTEGER
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id TEXT,
        details TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS admin_qr_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cloudinary_url TEXT NOT NULL,
        cloudinary_public_id TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 0,
        label TEXT,
        created_by INTEGER,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        deactivated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
    CREATE INDEX IF NOT EXISTS idx_products_seller ON products(seller_id);
    CREATE INDEX IF NOT EXISTS idx_products_featured ON products(is_featured, is_active);
    CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id);
    CREATE INDEX IF NOT EXISTS idx_repair_tickets_ticket_id ON repair_tickets(ticket_id);
    CREATE INDEX IF NOT EXISTS idx_trips_status ON trips(status);
    CREATE INDEX IF NOT EXISTS idx_trip_locations_trip ON trip_location_updates(trip_id);
    CREATE INDEX IF NOT EXISTS idx_commissions_seller ON seller_commissions(seller_id, status);
    CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);
    """

    # Split and execute statements
    statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
    for stmt in statements:
        try:
            execute(stmt)
        except Exception as e:
            logger.warning("Schema statement warning: %s — %s", e, stmt[:80])

    # Seed default categories and settings
    _seed_defaults()
    ensure_admin_user()
    ensure_extra_columns()
    logger.info("Database schema initialized")


def _seed_defaults():
    """Insert default categories and website settings if empty."""
    count = fetch_value("SELECT COUNT(*) FROM categories")
    if count == 0:
        categories = [
            ("Smartphones", "smartphones", "All smartphones", 1),
            ("Feature Phones", "feature-phones", "Basic feature phones", 2),
            ("Tablets", "tablets", "Tablets and iPads", 3),
            ("Accessories", "accessories", "Phone accessories", 4),
        ]
        for name, slug, desc, order in categories:
            execute(
                "INSERT INTO categories (name, slug, description, sort_order) VALUES (?, ?, ?, ?)",
                (name, slug, desc, order),
            )

    count = fetch_value("SELECT COUNT(*) FROM website_settings")
    if count == 0:
        defaults = [
            ("site_name", "Mobile Clinic Urlabari", "string"),
            ("tagline", "Second-hand Smartphones & Expert Mobile Repair", "string"),
            ("theme_primary", "#1e40af", "string"),
            ("theme_secondary", "#3b82f6", "string"),
            ("theme_accent", "#60a5fa", "string"),
            ("maintenance_mode", "0", "boolean"),
            ("currency", "NPR", "string"),
            ("timezone", "Asia/Kathmandu", "string"),
            ("contact_email", "bishal2014nir@gmail.com", "string"),
            ("contact_phone", "9819378583", "string"),
            ("whatsapp_number", "9819378583", "string"),
            ("footer_about", "Mobile Clinic in Urlabari, Morang — buy & sell second-hand smartphones, exchange and professional mobile repair with pickup in Nepal.", "text"),
            ("meta_title", "Mobile Clinic Urlabari | Second-hand Phones & Mobile Repair", "string"),
            ("meta_description", "Mobile Clinic Urlabari — second-hand smartphones, phone exchange, and mobile repair with pickup & delivery in Morang, Nepal.", "string"),
            ("tagline", "Mobile Clinic Urlabari — buy, sell, exchange & repair smartphones", "string"),
        ]
        for key, value, stype in defaults:
            execute(
                "INSERT INTO website_settings (setting_key, setting_value, setting_type) VALUES (?, ?, ?)",
                (key, value, stype),
            )


def ensure_admin_user():
    """Create default admin if none exists (auto seed)."""
    try:
        existing = fetch_one("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        if existing:
            return
        import os
        from app.utils.security import hash_password
        from app.utils.helpers import generate_uuid
        email = os.getenv("ADMIN_EMAIL", "bishal2014nir@gmail.com")
        password = os.getenv("ADMIN_PASSWORD", "mcl_admin123")
        mobile = os.getenv("ADMIN_MOBILE", "9819378583")
        name = os.getenv("ADMIN_NAME", "Bishal Niraula")
        execute(
            """INSERT INTO users (uuid, email, mobile, password_hash, full_name, role, is_active, is_verified)
               VALUES (?, ?, ?, ?, ?, 'admin', 1, 1)""",
            (generate_uuid(), email, mobile, hash_password(password), name),
        )
        logger.info("Auto-seeded admin user: %s", email)
    except Exception as e:
        logger.warning("Admin auto-seed skipped: %s", e)


def ensure_extra_columns():
    """Additive columns for features not in original CREATE TABLE."""
    alters = [
        "ALTER TABLE products ADD COLUMN min_qr_amount REAL",
        "ALTER TABLE orders ADD COLUMN payment_reference TEXT",
        "ALTER TABLE orders ADD COLUMN payment_amount_claimed REAL",
        "ALTER TABLE orders ADD COLUMN payment_proof_url TEXT",
        "ALTER TABLE users ADD COLUMN bio TEXT",
        "ALTER TABLE users ADD COLUMN shop_name TEXT",
        "ALTER TABLE users ADD COLUMN seller_qr_url TEXT",
        "ALTER TABLE users ADD COLUMN seller_qr_public_id TEXT",
        "ALTER TABLE products ADD COLUMN allows_exchange INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN exchange_requirements TEXT",
        "ALTER TABLE exchange_requests ADD COLUMN offer_photos TEXT",
        "ALTER TABLE exchange_requests ADD COLUMN offered_brand TEXT",
        "ALTER TABLE exchange_requests ADD COLUMN offered_model TEXT",
        "ALTER TABLE exchange_requests ADD COLUMN offered_condition TEXT",
        "ALTER TABLE exchange_requests ADD COLUMN lister_id INTEGER",
    ]
    for sql in alters:
        try:
            execute(sql)
        except Exception:
            pass  # column already exists

