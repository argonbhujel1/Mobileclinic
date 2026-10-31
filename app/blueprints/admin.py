from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.utils.helpers import admin_required, generate_uuid
from app.services.image_service import (
    upload_file_to_cloudinary,
    import_imgbb_url,
    save_product_image,
)
from app.services.commission_service import verify_commission_payment
from app.services.settings_service import get_settings, set_setting

admin_bp = Blueprint("admin", __name__)

ORDER_STATUSES = [
    "pending",
    "confirmed",
    "processing",
    "shipped",
    "delivered",
    "cancelled",
    "refunded",
]

# Admin handles full repair lifecycle including pickup & delivery (no separate staff required)
REPAIR_STATUSES = [
    "submitted",
    "accepted",
    "pickup_started",
    "phone_collected",
    "arrived_at_shop",
    "diagnosis",
    "awaiting_approval",
    "repair_in_progress",
    "repair_completed",
    "delivery_started",
    "delivered",
    "completed",
    "cancelled",
    "declined",
]

REPAIR_STATUS_LABELS = {
    "submitted": "Submitted (new)",
    "accepted": "Accepted by admin",
    "pickup_started": "Admin going for pickup",
    "phone_collected": "Phone collected",
    "arrived_at_shop": "At shop",
    "diagnosis": "Diagnosis",
    "awaiting_approval": "Awaiting customer approval",
    "repair_in_progress": "Repair in progress",
    "repair_completed": "Repair done",
    "delivery_started": "Admin delivering",
    "delivered": "Delivered to customer",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "declined": "Declined",
}

PHONE_CONDITIONS = ["Brand New", "Like New", "Excellent", "Good", "Fair", "For Parts"]


def _audit(action: str, entity_type: str = None, entity_id: str = None, details: str = None):
    try:
        db.execute(
            """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details, ip_address)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                current_user.id if current_user.is_authenticated else None,
                action,
                entity_type,
                str(entity_id) if entity_id is not None else None,
                details,
                request.remote_addr,
            ),
        )
    except Exception:
        pass


@admin_bp.route("/")
@login_required
@admin_required
def overview():
    def _safe_val(sql, default=0):
        try:
            return db.fetch_value(sql) or default
        except Exception:
            return default

    def _safe_all(sql, default=None):
        try:
            return db.fetch_all(sql) or (default or [])
        except Exception:
            return default or []

    stats = {
        "products": _safe_val("SELECT COUNT(*) FROM products WHERE is_active = 1"),
        "orders": _safe_val("SELECT COUNT(*) FROM orders"),
        "customers": _safe_val("SELECT COUNT(*) FROM users WHERE role = 'customer'"),
        "sellers": _safe_val("SELECT COUNT(*) FROM users WHERE role = 'seller'"),
        "repairs": _safe_val(
            "SELECT COUNT(*) FROM repair_tickets WHERE status NOT IN ('completed','cancelled','declined')"
        ),
        "pending_commissions": _safe_val(
            "SELECT COALESCE(SUM(commission_amount - paid_amount),0) FROM seller_commissions WHERE status IN ('pending','partial','overdue')"
        ),
    }
    recent_orders = _safe_all("SELECT * FROM orders ORDER BY created_at DESC LIMIT 8")
    return render_template("dashboard/admin/overview.html", stats=stats, recent_orders=recent_orders)


# ─── Phones ───────────────────────────────────────────────────────────────────

@admin_bp.route("/phones")
@login_required
@admin_required
def phones():
    products = db.fetch_all(
        """SELECT p.*, u.full_name AS seller_name FROM products p
           LEFT JOIN users u ON p.seller_id = u.id ORDER BY p.created_at DESC LIMIT 100"""
    )
    return render_template("dashboard/admin/phones.html", products=products)


@admin_bp.route("/phones/add", methods=["GET", "POST"])
@login_required
@admin_required
def phone_add():
    if request.method == "POST":
        allows_exchange = 1 if request.form.get("allows_exchange") else 0
        exchange_requirements = request.form.get("exchange_requirements", "").strip()
        title = request.form.get("title", "").strip()
        brand = request.form.get("brand", "").strip()
        model = request.form.get("model", "").strip()
        variant = request.form.get("variant", "").strip()
        ram = request.form.get("ram", "").strip()
        storage = request.form.get("storage", "").strip()
        condition = request.form.get("condition", "").strip()
        price = request.form.get("selling_price", type=float)
        negotiable = 1 if request.form.get("is_negotiable") else 0
        description = request.form.get("description", "").strip()
        imei = request.form.get("imei_serial", "").strip()
        category_id = request.form.get("category_id", type=int)
        warranty = request.form.get("warranty_status", "No Warranty")
        warranty_details = request.form.get("warranty_details", "")
        accessories = request.form.get("accessories", "No Accessories")
        location = request.form.get("location", "").strip()
        stock = request.form.get("stock_quantity", 1, type=int)
        payment_method = request.form.get("payment_method", "both")
        is_featured = 1 if request.form.get("is_featured") else 0
        min_qr_raw = request.form.get("min_qr_amount", "").strip()
        try:
            min_qr_amount = float(min_qr_raw) if min_qr_raw else (price or 0)
        except ValueError:
            min_qr_amount = price or 0

        if not all([title, brand, model, condition, price, description, location]):
            flash("Please fill all required fields.", "error")
            return redirect(url_for("admin.phone_add"))

        product_uuid = generate_uuid()
        db.execute(
            """INSERT INTO products
               (uuid, seller_id, is_admin_listing, title, brand, model, variant, ram, storage, condition,
                selling_price, is_negotiable, description, imei_serial, category_id, warranty_status,
                warranty_details, accessories, location, stock_quantity, payment_method, is_featured, is_active, min_qr_amount)
               VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                product_uuid,
                current_user.id,
                title,
                brand,
                model,
                variant,
                ram,
                storage,
                condition,
                price,
                negotiable,
                description,
                imei,
                category_id,
                warranty,
                warranty_details,
                accessories,
                location,
                stock,
                payment_method,
                is_featured,
                min_qr_amount,
            ),
        )
        row = db.fetch_one("SELECT id FROM products WHERE uuid = ?", (product_uuid,))
        product_id = row["id"] if row else None
        if product_id:
            try:
                db.execute(
                    "UPDATE products SET allows_exchange = ?, exchange_requirements = ? WHERE id = ?",
                    (allows_exchange, exchange_requirements, product_id),
                )
            except Exception:
                pass
        if not product_id:
            flash("Product created but could not resolve ID.", "warning")
            return redirect(url_for("admin.phones"))

        files = request.files.getlist("photos")
        uploaded = 0
        for i, f in enumerate(files):
            if f and f.filename:
                try:
                    result = upload_file_to_cloudinary(f, folder="mobile-clinic/products")
                    if result and result.get("url"):
                        save_product_image(product_id, result, display_order=i, is_primary=(uploaded == 0))
                        uploaded += 1
                except Exception as e:
                    flash(f"Image upload error: {e}", "error")

        imgbb = request.form.get("imgbb_url", "").strip()
        if imgbb:
            try:
                result = import_imgbb_url(imgbb, folder="mobile-clinic/products")
                if result and result.get("url"):
                    save_product_image(product_id, result, display_order=uploaded, is_primary=(uploaded == 0))
                    uploaded += 1
            except Exception as e:
                flash(f"URL import error: {e}", "error")

        _audit("phone_create", "product", product_id, title)
        flash(f"Phone listed successfully ({uploaded} photo(s)).", "success")
        return redirect(url_for("admin.phones"))

    categories = db.fetch_all("SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order")
    return render_template(
        "dashboard/admin/phone_form.html",
        categories=categories,
        conditions=PHONE_CONDITIONS,
        product=None,
    )


@admin_bp.route("/phones/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def phone_edit(product_id):
    product = db.fetch_one("SELECT * FROM products WHERE id = ?", (product_id,))
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("admin.phones"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        brand = request.form.get("brand", "").strip()
        model = request.form.get("model", "").strip()
        variant = request.form.get("variant", "").strip()
        ram = request.form.get("ram", "").strip()
        storage = request.form.get("storage", "").strip()
        condition = request.form.get("condition", "").strip()
        price = request.form.get("selling_price", type=float)
        negotiable = 1 if request.form.get("is_negotiable") else 0
        description = request.form.get("description", "").strip()
        imei = request.form.get("imei_serial", "").strip()
        category_id = request.form.get("category_id", type=int)
        warranty = request.form.get("warranty_status", "No Warranty")
        warranty_details = request.form.get("warranty_details", "")
        accessories = request.form.get("accessories", "No Accessories")
        location = request.form.get("location", "").strip()
        stock = request.form.get("stock_quantity", 1, type=int)
        payment_method = request.form.get("payment_method", "both")
        is_featured = 1 if request.form.get("is_featured") else 0
        is_active = 1 if request.form.get("is_active") else 0
        allows_exchange = 1 if request.form.get("allows_exchange") else 0
        exchange_requirements = request.form.get("exchange_requirements", "").strip()
        min_qr_raw = request.form.get("min_qr_amount", "").strip()
        try:
            min_qr_amount = float(min_qr_raw) if min_qr_raw else (price or 0)
        except ValueError:
            min_qr_amount = price or 0

        if not all([title, brand, model, condition, price, description, location]):
            flash("Please fill all required fields.", "error")
            return redirect(url_for("admin.phone_edit", product_id=product_id))

        try:
            db.execute(
                """UPDATE products SET title=?, brand=?, model=?, variant=?, ram=?, storage=?, condition=?,
                   selling_price=?, is_negotiable=?, description=?, imei_serial=?, category_id=?,
                   warranty_status=?, warranty_details=?, accessories=?, location=?, stock_quantity=?,
                   payment_method=?, is_featured=?, is_active=?, min_qr_amount=?, updated_at=datetime('now')
                   WHERE id=?""",
                (
                    title, brand, model, variant, ram, storage, condition, price, negotiable,
                    description, imei, category_id, warranty, warranty_details, accessories,
                    location, stock, payment_method, is_featured, is_active, min_qr_amount, product_id,
                ),
            )
        except Exception as e:
            # Fallback if min_qr_amount column missing on remote DB
            try:
                db.execute(
                    """UPDATE products SET title=?, brand=?, model=?, variant=?, ram=?, storage=?, condition=?,
                       selling_price=?, is_negotiable=?, description=?, imei_serial=?, category_id=?,
                       warranty_status=?, warranty_details=?, accessories=?, location=?, stock_quantity=?,
                       payment_method=?, is_featured=?, is_active=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (
                        title, brand, model, variant, ram, storage, condition, price, negotiable,
                        description, imei, category_id, warranty, warranty_details, accessories,
                        location, stock, payment_method, is_featured, is_active, product_id,
                    ),
                )
            except Exception as e2:
                flash(f"Could not save product: {e2}", "error")
                return redirect(url_for("admin.phone_edit", product_id=product_id))


        try:
            db.execute(
                "UPDATE products SET allows_exchange = ?, exchange_requirements = ? WHERE id = ?",
                (allows_exchange, exchange_requirements, product_id),
            )
        except Exception:
            pass

        files = request.files.getlist("photos")
        existing_count = db.fetch_value(
            "SELECT COUNT(*) FROM product_images WHERE product_id = ?", (product_id,)
        ) or 0
        uploaded = 0
        for i, f in enumerate(files):
            if f and f.filename:
                try:
                    result = upload_file_to_cloudinary(f, folder="mobile-clinic/products")
                    if result and result.get("url"):
                        save_product_image(
                            product_id, result,
                            display_order=existing_count + uploaded,
                            is_primary=(existing_count == 0 and uploaded == 0),
                        )
                        uploaded += 1
                except Exception as e:
                    flash(f"Image upload error: {e}", "error")

        imgbb = request.form.get("imgbb_url", "").strip()
        if imgbb:
            try:
                result = import_imgbb_url(imgbb, folder="mobile-clinic/products")
                if result and result.get("url"):
                    save_product_image(
                        product_id, result,
                        display_order=existing_count + uploaded,
                        is_primary=(existing_count == 0 and uploaded == 0),
                    )
                    uploaded += 1
            except Exception as e:
                flash(f"URL import error: {e}", "error")

        _audit("phone_edit", "product", product_id, title)
        flash(f"Product updated ({uploaded} new photo(s)).", "success")
        return redirect(url_for("admin.phones"))

    images = db.fetch_all(
        "SELECT * FROM product_images WHERE product_id = ? ORDER BY is_primary DESC, display_order",
        (product_id,),
    )
    categories = db.fetch_all("SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order")
    return render_template(
        "dashboard/admin/phone_form.html",
        categories=categories,
        conditions=PHONE_CONDITIONS,
        product=product,
        images=images,
    )




@admin_bp.route("/phones/<int:product_id>/images/<int:image_id>/delete", methods=["POST"])
@login_required
@admin_required
def phone_image_delete(product_id, image_id):
    img = db.fetch_one(
        "SELECT * FROM product_images WHERE id = ? AND product_id = ?",
        (image_id, product_id),
    )
    if not img:
        flash("Image not found.", "error")
        return redirect(url_for("admin.phone_edit", product_id=product_id))
    if img.get("cloudinary_public_id"):
        try:
            delete_cloudinary_image(img["cloudinary_public_id"])
        except Exception:
            pass
    was_primary = bool(img.get("is_primary"))
    db.execute("DELETE FROM product_images WHERE id = ?", (image_id,))
    if was_primary:
        nxt = db.fetch_one(
            "SELECT id FROM product_images WHERE product_id = ? ORDER BY display_order, id LIMIT 1",
            (product_id,),
        )
        if nxt:
            db.execute("UPDATE product_images SET is_primary = 1 WHERE id = ?", (nxt["id"],))
    _audit("phone_image_delete", "product", product_id, f"image {image_id}")
    flash("Photo removed.", "success")
    return redirect(url_for("admin.phone_edit", product_id=product_id))

@admin_bp.route("/phones/<int:product_id>/toggle", methods=["POST"])
@login_required
@admin_required
def phone_toggle(product_id):
    product = db.fetch_one("SELECT id, is_active, title FROM products WHERE id = ?", (product_id,))
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("admin.phones"))
    new_val = 0 if product["is_active"] else 1
    db.execute(
        "UPDATE products SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
        (new_val, product_id),
    )
    _audit("phone_toggle", "product", product_id, f"is_active={new_val}")
    flash(f"{'Activated' if new_val else 'Deactivated'}: {product['title']}", "success")
    return redirect(url_for("admin.phones"))


@admin_bp.route("/phones/<int:product_id>/delete", methods=["POST"])
@login_required
@admin_required
def phone_delete(product_id):
    product = db.fetch_one("SELECT id, title FROM products WHERE id = ?", (product_id,))
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("admin.phones"))
    # Remove dependents first (FK-safe)
    for sql in (
        "DELETE FROM product_images WHERE product_id = ?",
        "DELETE FROM order_items WHERE product_id = ?",
    ):
        try:
            db.execute(sql, (product_id,))
        except Exception:
            pass
    try:
        db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        _audit("phone_delete", "product", product_id, product.get("title") or str(product_id))
        flash("Phone deleted.", "success")
    except Exception as e:
        # Soft-delete fallback
        try:
            db.execute(
                "UPDATE products SET is_active = 0, is_hidden = 1, updated_at = datetime('now') WHERE id = ?",
                (product_id,),
            )
            flash("Could not hard-delete (linked orders). Product hidden instead.", "warning")
        except Exception as e2:
            flash(f"Delete failed: {e2}", "error")
    return redirect(url_for("admin.phones"))

    db.execute("DELETE FROM product_images WHERE product_id = ?", (product_id,))
    db.execute("DELETE FROM products WHERE id = ?", (product_id,))
    _audit("phone_delete", "product", product_id, product["title"])
    flash(f"Deleted: {product['title']}", "success")
    return redirect(url_for("admin.phones"))


# ─── Orders ───────────────────────────────────────────────────────────────────

@admin_bp.route("/orders")
@login_required
@admin_required
def orders():
    orders_list = db.fetch_all(
        """SELECT o.*, u.full_name AS buyer_name, u.email AS buyer_email,
              u.profile_photo_url AS buyer_photo, u.mobile AS buyer_mobile
           FROM orders o LEFT JOIN users u ON o.user_id = u.id
           ORDER BY o.created_at DESC LIMIT 100"""
    )
    return render_template(
        "dashboard/admin/orders.html",
        orders=orders_list,
        statuses=ORDER_STATUSES,
    )


@admin_bp.route("/orders/<int:order_id>/status", methods=["POST"])
@login_required
@admin_required
def order_status(order_id):
    status = request.form.get("status", "").strip()
    if status not in ORDER_STATUSES:
        flash("Invalid status.", "error")
        return redirect(url_for("admin.orders"))
    order = db.fetch_one("SELECT id, order_id, status FROM orders WHERE id = ?", (order_id,))
    if not order:
        flash("Order not found.", "error")
        return redirect(url_for("admin.orders"))
    db.execute(
        "UPDATE orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, order_id),
    )
    payment_status = request.form.get("payment_status", "").strip()
    if payment_status in ("pending", "awaiting_verification", "paid", "failed", "refunded", "cod"):
        db.execute(
            "UPDATE orders SET payment_status = ?, updated_at = datetime('now') WHERE id = ?",
            (payment_status, order_id),
        )
        # When QR payment verified as paid, auto-confirm order if still pending
        if payment_status == "paid" and status == "pending":
            status = "confirmed"
            db.execute(
                "UPDATE orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (status, order_id),
            )
        if payment_status == "paid":
            try:
                db.execute(
                    "UPDATE payments SET status = 'verified', verified_by = ?, verified_at = datetime('now') WHERE order_id = ? AND status = 'pending'",
                    (current_user.id, order_id),
                )
            except Exception:
                pass
    _audit("order_status", "order", order_id, f"{order['status']} → {status} / pay={payment_status}")
    flash(f"Order {order['order_id']} → {status} (payment: {payment_status or order.get('payment_status')})", "success")
    return redirect(url_for("admin.orders"))


# ─── Customers ────────────────────────────────────────────────────────────────

@admin_bp.route("/customers")
@login_required
@admin_required
def customers():
    users = db.fetch_all(
        "SELECT * FROM users WHERE role = 'customer' ORDER BY created_at DESC LIMIT 100"
    )
    return render_template("dashboard/admin/customers.html", users=users)


@admin_bp.route("/customers/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def customer_edit(user_id):
    user = db.fetch_one("SELECT * FROM users WHERE id = ? AND role = 'customer'", (user_id,))
    if not user:
        flash("Customer not found.", "error")
        return redirect(url_for("admin.customers"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        mobile = request.form.get("mobile", "").strip()
        address = request.form.get("address", "").strip()
        is_active = 1 if request.form.get("is_active") else 0
        is_verified = 1 if request.form.get("is_verified") else 0
        restricted = 1 if request.form.get("restricted") else 0
        restriction_reason = request.form.get("restriction_reason", "").strip()

        if not full_name or not email:
            flash("Name and email are required.", "error")
            return redirect(url_for("admin.customer_edit", user_id=user_id))

        # Email uniqueness
        other = db.fetch_one(
            "SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id)
        )
        if other:
            flash("Email already used by another account.", "error")
            return redirect(url_for("admin.customer_edit", user_id=user_id))

        db.execute(
            """UPDATE users SET full_name = ?, email = ?, mobile = ?, address = ?,
               is_active = ?, is_verified = ?, restricted = ?, restriction_reason = ?,
               updated_at = datetime('now') WHERE id = ?""",
            (
                full_name,
                email,
                mobile,
                address,
                is_active,
                is_verified,
                restricted,
                restriction_reason or None,
                user_id,
            ),
        )
        _audit("customer_edit", "user", user_id, email)
        flash("Customer updated.", "success")
        return redirect(url_for("admin.customers"))

    return render_template("dashboard/admin/customer_edit.html", user=user)


@admin_bp.route("/customers/<int:user_id>/toggle", methods=["POST"])
@login_required
@admin_required
def customer_toggle(user_id):
    user = db.fetch_one("SELECT id, is_active, full_name FROM users WHERE id = ? AND role = 'customer'", (user_id,))
    if not user:
        flash("Customer not found.", "error")
        return redirect(url_for("admin.customers"))
    new_val = 0 if user["is_active"] else 1
    db.execute(
        "UPDATE users SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
        (new_val, user_id),
    )
    _audit("customer_toggle", "user", user_id, f"is_active={new_val}")
    flash(f"{'Activated' if new_val else 'Deactivated'}: {user['full_name']}", "success")
    return redirect(url_for("admin.customers"))


# ─── Sellers ──────────────────────────────────────────────────────────────────

@admin_bp.route("/sellers")
@login_required
@admin_required
def sellers():
    sellers_list = db.fetch_all("SELECT * FROM users WHERE role = 'seller' ORDER BY created_at DESC")
    apps = db.fetch_all(
        """SELECT sa.*, u.email FROM seller_applications sa JOIN users u ON sa.user_id = u.id
           WHERE sa.status = 'pending' ORDER BY sa.created_at"""
    )
    return render_template("dashboard/admin/sellers.html", sellers=sellers_list, applications=apps)


@admin_bp.route("/sellers/<int:user_id>/toggle", methods=["POST"])
@login_required
@admin_required
def seller_toggle(user_id):
    user = db.fetch_one("SELECT id, is_active, full_name FROM users WHERE id = ? AND role = 'seller'", (user_id,))
    if not user:
        flash("Seller not found.", "error")
        return redirect(url_for("admin.sellers"))
    new_val = 0 if user["is_active"] else 1
    db.execute(
        "UPDATE users SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
        (new_val, user_id),
    )
    _audit("seller_toggle", "user", user_id, f"is_active={new_val}")
    flash(f"{'Activated' if new_val else 'Deactivated'}: {user['full_name']}", "success")
    return redirect(url_for("admin.sellers"))


# ─── Repairs (admin does all steps including pickup & delivery) ────────────────

@admin_bp.route("/repairs")
@login_required
@admin_required
def repairs():
    tickets = db.fetch_all(
        """SELECT rt.*, u.full_name AS user_full_name, u.profile_photo_url AS user_photo,
              u.email AS user_email, u.mobile AS user_mobile
           FROM repair_tickets rt
           LEFT JOIN users u ON rt.user_id = u.id
           ORDER BY
             CASE WHEN rt.status IN ('completed','cancelled','declined') THEN 1 ELSE 0 END,
             rt.created_at DESC
           LIMIT 150"""
    )
    return render_template(
        "dashboard/admin/repairs.html",
        tickets=tickets,
        statuses=REPAIR_STATUSES,
        status_labels=REPAIR_STATUS_LABELS,
    )


@admin_bp.route("/repairs/<int:ticket_pk>/status", methods=["POST"])
@login_required
@admin_required
def repair_status(ticket_pk):
    status = request.form.get("status", "").strip()
    notes = request.form.get("notes", "").strip()
    if status not in REPAIR_STATUSES:
        flash("Invalid status.", "error")
        return redirect(url_for("admin.repairs"))
    ticket = db.fetch_one(
        "SELECT id, ticket_id, status FROM repair_tickets WHERE id = ?", (ticket_pk,)
    )
    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for("admin.repairs"))
    old = ticket["status"]
    db.execute(
        "UPDATE repair_tickets SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, ticket_pk),
    )
    label = REPAIR_STATUS_LABELS.get(status, status)
    hist_notes = notes or f"Admin: {old} → {label}"
    try:
        db.execute(
            """INSERT INTO repair_status_history (repair_ticket_id, status, notes, changed_by)
               VALUES (?, ?, ?, ?)""",
            (ticket_pk, status, hist_notes, current_user.id),
        )
    except Exception:
        pass

    # Live map trips: admin pickup / delivery
    full = db.fetch_one("SELECT * FROM repair_tickets WHERE id = ?", (ticket_pk,))
    if status in ("pickup_started", "delivery_started") and full:
        trip_type = "pickup" if status == "pickup_started" else "delivery"
        # end any other active trips on this ticket
        db.execute(
            """UPDATE trips SET status = 'completed', completed_at = datetime('now')
               WHERE repair_ticket_id = ? AND status IN ('pending','started','in_progress')""",
            (ticket_pk,),
        )
        dest_lat = full.get("pickup_latitude")
        dest_lng = full.get("pickup_longitude")
        dest_addr = full.get("pickup_address") or ""
        trip_uuid = generate_uuid()
        db.execute(
            """INSERT INTO trips (uuid, repair_ticket_id, staff_id, trip_type, status,
               destination_lat, destination_lng, destination_address, started_at)
               VALUES (?, ?, ?, ?, 'started', ?, ?, ?, datetime('now'))""",
            (
                trip_uuid,
                ticket_pk,
                current_user.id,
                trip_type,
                dest_lat,
                dest_lng,
                dest_addr,
            ),
        )
        hist_notes = (hist_notes or "") + f" · Live tracking started ({trip_type})"
        flash(f"Ticket {ticket['ticket_id']}: {label}. Open Live Map to share GPS.", "success")
        _audit("repair_status", "repair_ticket", ticket_pk, f"{old} → {status}")
        return redirect(url_for("admin.live_map"))
    elif status in ("phone_collected", "arrived_at_shop", "delivered", "completed", "cancelled", "declined"):
        db.execute(
            """UPDATE trips SET status = 'completed', completed_at = datetime('now')
               WHERE repair_ticket_id = ? AND status IN ('pending','started','in_progress')""",
            (ticket_pk,),
        )

    _audit("repair_status", "repair_ticket", ticket_pk, f"{old} → {status}")
    flash(f"Ticket {ticket['ticket_id']}: {label}", "success")
    return redirect(url_for("admin.repairs"))


@admin_bp.route("/live-map")
@login_required
@admin_required
def live_map():
    trips = db.fetch_all(
        """SELECT t.*, u.full_name AS staff_name, rt.ticket_id, rt.pickup_address,
              rt.pickup_latitude, rt.pickup_longitude, rt.guest_name, rt.guest_mobile,
              rt.phone_brand, rt.phone_model, rt.status AS ticket_status,
           (SELECT latitude FROM trip_location_updates WHERE trip_id = t.id ORDER BY recorded_at DESC LIMIT 1) AS last_lat,
           (SELECT longitude FROM trip_location_updates WHERE trip_id = t.id ORDER BY recorded_at DESC LIMIT 1) AS last_lng,
           (SELECT recorded_at FROM trip_location_updates WHERE trip_id = t.id ORDER BY recorded_at DESC LIMIT 1) AS last_update
           FROM trips t
           JOIN users u ON t.staff_id = u.id
           JOIN repair_tickets rt ON t.repair_ticket_id = rt.id
           WHERE t.status IN ('started','in_progress')
           ORDER BY t.started_at DESC"""
    )
    my_trips = [tr for tr in trips if tr.get("staff_id") == current_user.id]
    return render_template(
        "dashboard/admin/live_map.html",
        trips=trips,
        my_trips=my_trips,
    )


@admin_bp.route("/payments/qr", methods=["GET", "POST"])
@login_required
@admin_required
def admin_qr():
    if request.method == "POST":
        db.execute(
            "UPDATE admin_qr_codes SET is_active = 0, deactivated_at = datetime('now') WHERE is_active = 1"
        )
        result = None
        if "qr_image" in request.files and request.files["qr_image"].filename:
            try:
                result = upload_file_to_cloudinary(
                    request.files["qr_image"], folder="mobile-clinic/admin-qr"
                )
            except Exception as e:
                flash(str(e), "error")
        elif request.form.get("imgbb_url"):
            try:
                result = import_imgbb_url(
                    request.form["imgbb_url"], folder="mobile-clinic/admin-qr"
                )
            except Exception as e:
                flash(str(e), "error")
        if result:
            db.execute(
                """INSERT INTO admin_qr_codes (cloudinary_url, cloudinary_public_id, is_active, label, created_by)
                   VALUES (?, ?, 1, ?, ?)""",
                (
                    result["url"],
                    result["public_id"],
                    request.form.get("label", "Admin Commission QR"),
                    current_user.id,
                ),
            )
            flash("Admin QR updated and set as active.", "success")
        return redirect(url_for("admin.admin_qr"))
    current = db.fetch_one(
        "SELECT * FROM admin_qr_codes WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
    )
    history = db.fetch_all("SELECT * FROM admin_qr_codes ORDER BY created_at DESC LIMIT 10")
    return render_template("dashboard/admin/admin_qr.html", current=current, history=history)


@admin_bp.route("/payments/commissions")
@login_required
@admin_required
def commission_payments():
    payments = db.fetch_all(
        """SELECT cp.*, u.full_name AS seller_name, u.email AS seller_email
           FROM commission_payments cp JOIN users u ON cp.seller_id = u.id
           ORDER BY cp.created_at DESC LIMIT 50"""
    )
    return render_template("dashboard/admin/commission_payments.html", payments=payments)


@admin_bp.route("/payments/commissions/<int:payment_id>/verify", methods=["POST"])
@login_required
@admin_required
def verify_payment(payment_id):
    action = request.form.get("action")
    notes = request.form.get("notes", "")
    try:
        verify_commission_payment(
            payment_id, current_user.id, approve=(action == "approve"), notes=notes
        )
        flash("Payment processed.", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("admin.commission_payments"))


@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
@admin_required
def settings():
    if request.method == "POST":
        for key in [
            "site_name",
            "tagline",
            "theme_primary",
            "theme_secondary",
            "contact_email",
            "contact_phone",
            "whatsapp_number",
            "footer_about",
            "facebook_url",
            "instagram_url",
            "meta_title",
            "meta_description",
            "google_site_verification",
            "tiktok_embed_url",
        ]:
            if key in request.form:
                set_setting(key, request.form[key].strip(), current_user.id)
        if "maintenance_mode" in request.form:
            set_setting(
                "maintenance_mode",
                "1" if request.form.get("maintenance_mode") else "0",
                current_user.id,
            )
        if "logo" in request.files and request.files["logo"].filename:
            try:
                result = upload_file_to_cloudinary(
                    request.files["logo"], folder="mobile-clinic/branding"
                )
                set_setting("logo_url", result["url"], current_user.id)
                if result.get("public_id"):
                    set_setting("logo_public_id", result["public_id"], current_user.id)
                flash("Logo uploaded successfully.", "success")
            except Exception as e:
                flash(f"Logo upload failed: {e}", "error")
        elif request.form.get("logo_url_manual"):
            set_setting(
                "logo_url", request.form["logo_url_manual"].strip(), current_user.id
            )
            flash("Logo URL saved.", "success")
        # Favicon
        if "favicon" in request.files and request.files["favicon"].filename:
            try:
                result = upload_file_to_cloudinary(
                    request.files["favicon"], folder="mobile-clinic/branding"
                )
                set_setting("favicon_url", result["url"], current_user.id)
                if result.get("public_id"):
                    set_setting("favicon_public_id", result["public_id"], current_user.id)
                flash("Favicon uploaded successfully.", "success")
            except Exception as e:
                flash(f"Favicon upload failed: {e}", "error")
        elif request.form.get("favicon_url_manual"):
            set_setting(
                "favicon_url", request.form["favicon_url_manual"].strip(), current_user.id
            )
            flash("Favicon URL saved.", "success")
        flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))
    settings_data = get_settings()
    return render_template("dashboard/admin/settings.html", settings=settings_data)


@admin_bp.route("/audit-logs")
@login_required
@admin_required
def audit_logs():
    logs = db.fetch_all("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 100")
    return render_template("dashboard/admin/audit_logs.html", logs=logs)

@admin_bp.route("/exchanges")
@login_required
@admin_required
def exchanges():
    rows = db.fetch_all(
        """SELECT er.*, p.title AS product_title
           FROM exchange_requests er
           LEFT JOIN products p ON er.desired_product_id = p.id
           ORDER BY er.created_at DESC LIMIT 150"""
    )
    return render_template("dashboard/admin/exchanges.html", rows=rows)

@admin_bp.route("/exchanges/add", methods=["GET", "POST"])
@login_required
@admin_required
def exchange_phone_add():
    """Simple exchange-only listing: name, model, photos, requirements."""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        brand = request.form.get("brand", "").strip()
        model = request.form.get("model", "").strip()
        condition = request.form.get("condition", "Good").strip()
        description = request.form.get("description", "").strip()
        requirements = request.form.get("exchange_requirements", "").strip()
        location = request.form.get("location", "Urlabari").strip() or "Urlabari"
        if not title or not brand or not model:
            flash("Title, brand and model are required.", "error")
            return redirect(url_for("admin.exchange_phone_add"))
        product_uuid = generate_uuid()
        try:
            db.execute(
                """INSERT INTO products
                   (uuid, seller_id, is_admin_listing, title, brand, model, condition,
                    selling_price, description, location, stock_quantity, payment_method,
                    is_featured, is_active, allows_exchange, exchange_requirements)
                   VALUES (?, ?, 1, ?, ?, ?, ?, 0, ?, ?, 1, 'both', 0, 1, 1, ?)""",
                (product_uuid, current_user.id, title, brand, model, condition,
                 description or requirements, location, requirements),
            )
        except Exception as e:
            try:
                db.execute(
                    """INSERT INTO products
                       (uuid, seller_id, is_admin_listing, title, brand, model, condition,
                        selling_price, description, location, stock_quantity, payment_method,
                        is_featured, is_active)
                       VALUES (?, ?, 1, ?, ?, ?, ?, 0, ?, ?, 1, 'both', 0, 1)""",
                    (product_uuid, current_user.id, title, brand, model, condition,
                     description or requirements, location),
                )
            except Exception as e2:
                flash(str(e2), "error")
                return redirect(url_for("admin.exchange_phone_add"))
        row = db.fetch_one("SELECT id FROM products WHERE uuid = ?", (product_uuid,))
        product_id = row["id"] if row else None
        if product_id:
            try:
                db.execute(
                    "UPDATE products SET allows_exchange = 1, exchange_requirements = ? WHERE id = ?",
                    (requirements, product_id),
                )
            except Exception:
                pass
            from app.services.image_service import save_product_image
            for i, f in enumerate(request.files.getlist("photos")):
                if f and f.filename:
                    try:
                        result = upload_file_to_cloudinary(f, folder="mobile-clinic/exchange-list")
                        if result and result.get("url"):
                            save_product_image(product_id, result, display_order=i, is_primary=(i == 0))
                    except Exception as e:
                        flash(str(e), "error")
        flash("Exchange listing created.", "success")
        return redirect(url_for("admin.exchanges"))
    return render_template(
        "dashboard/admin/exchange_form.html",
        conditions=PHONE_CONDITIONS,
    )
