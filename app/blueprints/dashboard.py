from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.utils.helpers import role_required, generate_uuid, normalize_name_for_username, now_kathmandu
from app.utils.security import hash_password
from datetime import timedelta
from app.services.commission_service import get_outstanding_balance, get_active_admin_qr, submit_commission_payment
from app.services.image_service import upload_file_to_cloudinary, import_imgbb_url, save_profile_photo
from app.services.email_service import send_seller_credentials

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/customer")
@login_required
def customer():
    if current_user.role not in ("customer", "seller", "admin"):
        flash("Access denied.", "error")
        return redirect(url_for("main.home"))
    orders = db.fetch_all(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (current_user.id,),
    )
    repairs = db.fetch_all(
        "SELECT * FROM repair_tickets WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (current_user.id,),
    )
    notifications = db.fetch_all(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (current_user.id,),
    )
    return render_template("dashboard/customer/overview.html", orders=orders, repairs=repairs, notifications=notifications)


@dashboard_bp.route("/customer/be-seller", methods=["GET", "POST"])
@login_required
def be_seller():
    if current_user.role == "seller":
        flash("You are already a seller.", "info")
        return redirect(url_for("dashboard.seller"))
    if request.method == "POST":
        existing = db.fetch_one(
            "SELECT id FROM seller_applications WHERE user_id = ? AND status = 'pending'",
            (current_user.id,),
        )
        if existing:
            flash("You already have a pending application.", "info")
            return redirect(url_for("dashboard.customer"))
        name = request.form.get("full_name") or current_user.full_name
        mobile = request.form.get("mobile") or current_user.mobile
        username_base = "mblclc_" + normalize_name_for_username(name)
        # uniqueness
        username = username_base
        i = 1
        while db.fetch_one("SELECT id FROM users WHERE seller_username = ?", (username,)):
            username = f"{username_base}{i}"
            i += 1
        db.execute(
            """INSERT INTO seller_applications (user_id, full_name, mobile, email, status, requested_username)
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (current_user.id, name, mobile, current_user.email, username),
        )
        app_row = db.fetch_one(
            "SELECT id FROM seller_applications WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
            (current_user.id,),
        )
        app_id = app_row["id"] if app_row else None

        # Issue credentials immediately (no worker required)
        temp_password = f"mblclc_{mobile[-10:] if mobile else 'seller'}"
        pw_hash = hash_password(temp_password)
        db.execute(
            """UPDATE users SET role = 'seller', seller_username = ?, password_hash = ?,
               must_change_password = 1, is_active = 1, is_verified = 1, updated_at = datetime('now')
               WHERE id = ?""",
            (username, pw_hash, current_user.id),
        )
        if app_id:
            db.execute(
                "UPDATE seller_applications SET status = 'approved', processed_at = datetime('now') WHERE id = ?",
                (app_id,),
            )
            try:
                db.execute(
                    """INSERT INTO seller_credential_jobs
                       (application_id, user_id, username, password_plain_temp, status, scheduled_at, processed_at)
                       VALUES (?, ?, ?, '', 'sent', datetime('now'), datetime('now'))""",
                    (app_id, current_user.id, username),
                )
            except Exception:
                pass

        base = (current_app.config.get("APP_BASE_URL") or request.host_url or "http://127.0.0.1:5000").rstrip("/")
        login_url = f"{base}/auth/login"
        seller_url = f"{base}/dashboard/seller"
        sent = send_seller_credentials(
            current_user.email,
            username,
            temp_password,
            name,
            login_url=login_url,
            seller_panel_url=seller_url,
        )
        if sent:
            flash(
                f"Seller account created! Credentials sent to {current_user.email}. "
                f"Username: {username}. Check email for seller panel link.",
                "success",
            )
        else:
            flash(
                f"Seller account created. Email could not be sent — save these credentials: "
                f"Username: {username} / Password: {temp_password}. Login: {login_url}",
                "warning",
            )
        return redirect(url_for("dashboard.seller"))
    return render_template("dashboard/customer/be_seller.html")


@dashboard_bp.route("/customer/profile", methods=["GET", "POST"])
@dashboard_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Shared profile for customer / seller / admin — photo shown on products & admin panels."""
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        address = request.form.get("address", "").strip()
        bio = request.form.get("bio", "").strip()
        shop_name = request.form.get("shop_name", "").strip()
        if full_name:
            try:
                db.execute(
                    """UPDATE users SET full_name = ?, mobile = ?, address = ?, bio = ?, shop_name = ?,
                       updated_at = datetime('now') WHERE id = ?""",
                    (full_name, mobile, address, bio, shop_name, current_user.id),
                )
            except Exception:
                db.execute(
                    "UPDATE users SET full_name = ?, mobile = ?, address = ?, updated_at = datetime('now') WHERE id = ?",
                    (full_name, mobile, address, current_user.id),
                )
            flash("Profile updated.", "success")
        if "photo" in request.files and request.files["photo"].filename:
            try:
                result = upload_file_to_cloudinary(request.files["photo"], folder="mobile-clinic/profiles")
                if result:
                    save_profile_photo(current_user.id, result)
                    flash("Profile photo updated.", "success")
            except Exception as e:
                flash(str(e), "error")
        imgbb = request.form.get("imgbb_url", "").strip()
        if imgbb:
            try:
                result = import_imgbb_url(imgbb, folder="mobile-clinic/profiles")
                if result:
                    save_profile_photo(current_user.id, result)
                    flash("Profile photo imported.", "success")
            except Exception as e:
                flash(str(e), "error")
        # Seller payment QR
        if current_user.role in ("seller", "admin"):
            if "seller_qr" in request.files and request.files["seller_qr"].filename:
                try:
                    result = upload_file_to_cloudinary(
                        request.files["seller_qr"], folder="mobile-clinic/seller-qr"
                    )
                    if result and result.get("url"):
                        try:
                            db.execute(
                                """UPDATE users SET seller_qr_url = ?, seller_qr_public_id = ?,
                                   updated_at = datetime('now') WHERE id = ?""",
                                (result["url"], result.get("public_id"), current_user.id),
                            )
                        except Exception:
                            db.execute(
                                "UPDATE users SET seller_qr_url = ?, updated_at = datetime('now') WHERE id = ?",
                                (result["url"], current_user.id),
                            )
                        flash("Payment QR saved. Buyers will see this for your listings.", "success")
                except Exception as e:
                    flash(f"QR upload failed: {e}", "error")
            elif request.form.get("seller_qr_url_manual", "").strip():
                url = request.form.get("seller_qr_url_manual", "").strip()
                try:
                    db.execute(
                        "UPDATE users SET seller_qr_url = ?, updated_at = datetime('now') WHERE id = ?",
                        (url, current_user.id),
                    )
                except Exception:
                    pass
                flash("Payment QR URL saved.", "success")
        return redirect(url_for("dashboard.profile"))
    user = db.fetch_one("SELECT * FROM users WHERE id = ?", (current_user.id,))
    return render_template("dashboard/customer/profile.html", user=user)


@dashboard_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not current_user.check_password(current):
            flash("Current password is incorrect.", "error")
        elif len(new) < 8 or new != confirm:
            flash("New passwords must match and be at least 8 characters.", "error")
        else:
            db.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = datetime('now') WHERE id = ?",
                (hash_password(new), current_user.id),
            )
            flash("Password changed successfully.", "success")
            return redirect(url_for("dashboard.customer"))
    return render_template("dashboard/change_password.html")


# ---- Seller Dashboard ----
@dashboard_bp.route("/seller")
@login_required
@role_required("seller", "admin")
def seller():
    listings = db.fetch_all(
        "SELECT * FROM products WHERE seller_id = ? ORDER BY created_at DESC LIMIT 20",
        (current_user.id,),
    )
    outstanding = get_outstanding_balance(current_user.id)
    commissions = db.fetch_all(
        "SELECT * FROM seller_commissions WHERE seller_id = ? ORDER BY created_at DESC LIMIT 10",
        (current_user.id,),
    )
    return render_template(
        "dashboard/seller/overview.html",
        listings=listings,
        outstanding=outstanding,
        commissions=commissions,
    )


@dashboard_bp.route("/seller/add-phone", methods=["GET", "POST"])
@login_required
@role_required("seller", "admin")
def seller_add_phone():
    if request.method == "POST":
        # Collect 19 fields
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
        min_qr_raw = request.form.get("min_qr_amount", "").strip()
        try:
            min_qr_amount = float(min_qr_raw) if min_qr_raw else (price or 0)
        except ValueError:
            min_qr_amount = price or 0

        if not all([title, brand, model, condition, price, description, location]):
            flash("Please fill all required fields.", "error")
            return redirect(url_for("dashboard.seller_add_phone"))

        is_admin = 1 if current_user.is_admin() else 0
        is_featured = 1 if is_admin else 0
        product_uuid = generate_uuid()
        try:
            db.execute(
                """INSERT INTO products
                   (uuid, seller_id, is_admin_listing, title, brand, model, variant, ram, storage, condition,
                    selling_price, is_negotiable, description, imei_serial, category_id, warranty_status,
                    warranty_details, accessories, location, stock_quantity, payment_method, is_featured, is_active, min_qr_amount)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (product_uuid, current_user.id, is_admin, title, brand, model, variant, ram, storage, condition,
                 price, negotiable, description, imei, category_id, warranty, warranty_details, accessories,
                 location, stock, payment_method, is_featured, min_qr_amount),
            )
        except Exception:
            db.execute(
                """INSERT INTO products
                   (uuid, seller_id, is_admin_listing, title, brand, model, variant, ram, storage, condition,
                    selling_price, is_negotiable, description, imei_serial, category_id, warranty_status,
                    warranty_details, accessories, location, stock_quantity, payment_method, is_featured, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (product_uuid, current_user.id, is_admin, title, brand, model, variant, ram, storage, condition,
                 price, negotiable, description, imei, category_id, warranty, warranty_details, accessories,
                 location, stock, payment_method, is_featured),
            )
        row = db.fetch_one("SELECT id FROM products WHERE uuid = ?", (product_uuid,))
        product_id = row["id"] if row else None
        allows_exchange = 1 if request.form.get("allows_exchange") else 0
        exchange_requirements = request.form.get("exchange_requirements", "").strip()
        if product_id:
            try:
                db.execute(
                    "UPDATE products SET allows_exchange = ?, exchange_requirements = ? WHERE id = ?",
                    (allows_exchange, exchange_requirements, product_id),
                )
            except Exception:
                pass
        if not product_id:
            flash("Product created but image attach failed (no product id).", "error")
            return redirect(url_for("dashboard.seller"))

        # Handle images
        files = request.files.getlist("photos")
        imgbb_urls = request.form.getlist("imgbb_urls")
        min_photos = current_app.config["MIN_ADMIN_PRODUCT_IMAGES"] if is_admin else current_app.config["MIN_SELLER_PRODUCT_IMAGES"]
        uploaded = 0
        from app.services.image_service import save_product_image
        for i, f in enumerate(files):
            if f and f.filename:
                try:
                    result = upload_file_to_cloudinary(f, folder="mobile-clinic/products")
                    save_product_image(product_id, result, display_order=i, is_primary=(i == 0))
                    uploaded += 1
                except Exception as e:
                    flash(f"Image upload error: {e}", "error")
        for i, url in enumerate(imgbb_urls):
            if url.strip():
                try:
                    result = import_imgbb_url(url.strip(), folder="mobile-clinic/products")
                    save_product_image(product_id, result, display_order=uploaded + i, is_primary=(uploaded + i == 0 and uploaded == 0))
                    uploaded += 1
                except Exception as e:
                    flash(f"ImgBB import error: {e}", "error")

        if uploaded < min_photos:
            flash(f"At least {min_photos} photos required. Listing created but may need more photos.", "warning")
        else:
            flash("Phone listed successfully!", "success")
        return redirect(url_for("dashboard.seller"))

    categories = db.fetch_all("SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order")
    return render_template("dashboard/seller/add_phone.html", categories=categories)


@dashboard_bp.route("/seller/pay-admin", methods=["GET", "POST"])
@login_required
@role_required("seller")
def pay_admin():
    outstanding = get_outstanding_balance(current_user.id)
    admin_qr = get_active_admin_qr()
    commissions = db.fetch_all(
        """SELECT * FROM seller_commissions
           WHERE seller_id = ? AND status IN ('pending','partial','overdue')
           ORDER BY created_at""",
        (current_user.id,),
    )
    if request.method == "POST":
        if not admin_qr:
            flash("Admin QR payment is currently unavailable. Please contact Mobile Clinic.", "error")
            return redirect(url_for("dashboard.pay_admin"))
        amount = request.form.get("amount", type=float)
        ref = request.form.get("transaction_ref", "").strip()
        receipt_result = None
        if "receipt" in request.files and request.files["receipt"].filename:
            try:
                receipt_result = upload_file_to_cloudinary(request.files["receipt"], folder="mobile-clinic/payments")
            except Exception as e:
                flash(str(e), "error")
                return redirect(url_for("dashboard.pay_admin"))
        try:
            submit_commission_payment(current_user.id, amount, ref, receipt_result)
            flash("Payment proof submitted. Awaiting Admin verification.", "success")
            # Notify admin (email/notification)
        except Exception as e:
            flash(str(e), "error")
        return redirect(url_for("dashboard.pay_admin"))

    history = db.fetch_all(
        "SELECT * FROM commission_payments WHERE seller_id = ? ORDER BY created_at DESC LIMIT 10",
        (current_user.id,),
    )
    return render_template(
        "dashboard/seller/pay_admin.html",
        outstanding=outstanding,
        admin_qr=admin_qr,
        commissions=commissions,
        history=history,
    )


@dashboard_bp.route("/staff")
@login_required
@role_required("staff", "admin")
def staff():
    assignments = db.fetch_all(
        """SELECT rt.*, t.uuid AS trip_uuid, t.status AS trip_status, t.trip_type
           FROM repair_tickets rt
           LEFT JOIN trips t ON t.repair_ticket_id = rt.id AND t.status IN ('pending','started','in_progress')
           WHERE rt.assigned_staff_id = ? AND rt.status NOT IN ('completed','cancelled','declined')
           ORDER BY rt.updated_at DESC""",
        (current_user.id,),
    )
    return render_template("dashboard/staff/overview.html", assignments=assignments)


@dashboard_bp.route("/seller/phones/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("seller", "admin")
def seller_edit_phone(product_id):
    product = db.fetch_one("SELECT * FROM products WHERE id = ?", (product_id,))
    if not product or (product["seller_id"] != current_user.id and current_user.role != "admin"):
        flash("Product not found.", "error")
        return redirect(url_for("dashboard.seller"))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        price = request.form.get("selling_price", type=float)
        description = request.form.get("description", "").strip()
        stock = request.form.get("stock_quantity", 1, type=int)
        is_active = 1 if request.form.get("is_active") else 0
        min_qr_raw = request.form.get("min_qr_amount", "").strip()
        try:
            min_qr_amount = float(min_qr_raw) if min_qr_raw else (price or 0)
        except ValueError:
            min_qr_amount = price or 0
        allows_exchange = 1 if request.form.get("allows_exchange") else 0
        exchange_requirements = request.form.get("exchange_requirements", "").strip()
        if title and price and description:
            try:
                db.execute(
                    """UPDATE products SET title=?, selling_price=?, description=?, stock_quantity=?, is_active=?,
                       min_qr_amount=?, updated_at=datetime('now') WHERE id=?""",
                    (title, price, description, stock, is_active, min_qr_amount, product_id),
                )
            except Exception:
                db.execute(
                    """UPDATE products SET title=?, selling_price=?, description=?, stock_quantity=?, is_active=?,
                       updated_at=datetime('now') WHERE id=?""",
                    (title, price, description, stock, is_active, product_id),
                )
            try:
                db.execute(
                    "UPDATE products SET allows_exchange = ?, exchange_requirements = ? WHERE id = ?",
                    (allows_exchange, exchange_requirements, product_id),
                )
            except Exception:
                pass
        files = request.files.getlist("photos")
        existing_count = db.fetch_value("SELECT COUNT(*) FROM product_images WHERE product_id = ?", (product_id,)) or 0
        uploaded = 0
        for i, f in enumerate(files):
            if f and f.filename:
                try:
                    result = upload_file_to_cloudinary(f, folder="mobile-clinic/products")
                    if result and result.get("url"):
                        save_product_image(product_id, result, display_order=existing_count + uploaded, is_primary=(existing_count == 0 and uploaded == 0))
                        uploaded += 1
                except Exception as e:
                    flash(str(e), "error")
        flash(f"Listing updated ({uploaded} new photo(s)).", "success")
        return redirect(url_for("dashboard.seller_edit_phone", product_id=product_id))
    images = db.fetch_all(
        "SELECT * FROM product_images WHERE product_id = ? ORDER BY is_primary DESC, display_order",
        (product_id,),
    )
    return render_template("dashboard/seller/edit_phone.html", product=product, images=images)


@dashboard_bp.route("/seller/phones/<int:product_id>/images/<int:image_id>/delete", methods=["POST"])
@login_required
@role_required("seller", "admin")
def seller_image_delete(product_id, image_id):
    product = db.fetch_one("SELECT * FROM products WHERE id = ?", (product_id,))
    if not product or (product["seller_id"] != current_user.id and current_user.role != "admin"):
        flash("Not allowed.", "error")
        return redirect(url_for("dashboard.seller"))
    img = db.fetch_one("SELECT * FROM product_images WHERE id = ? AND product_id = ?", (image_id, product_id))
    if img:
        if img.get("cloudinary_public_id"):
            try:
                delete_cloudinary_image(img["cloudinary_public_id"])
            except Exception:
                pass
        was_primary = bool(img.get("is_primary"))
        db.execute("DELETE FROM product_images WHERE id = ?", (image_id,))
        if was_primary:
            nxt = db.fetch_one("SELECT id FROM product_images WHERE product_id = ? ORDER BY display_order, id LIMIT 1", (product_id,))
            if nxt:
                db.execute("UPDATE product_images SET is_primary = 1 WHERE id = ?", (nxt["id"],))
        flash("Photo removed.", "success")
    return redirect(url_for("dashboard.seller_edit_phone", product_id=product_id))


@dashboard_bp.route("/seller/orders")
@login_required
@role_required("seller", "admin")
def seller_orders():
    """Orders that include this seller's products — verify QR payments here."""
    orders = db.fetch_all(
        """SELECT DISTINCT o.*,
              (SELECT GROUP_CONCAT(oi.product_title, ', ') FROM order_items oi
               WHERE oi.order_id = o.id AND oi.seller_id = ?) AS my_items
           FROM orders o
           JOIN order_items oi ON oi.order_id = o.id
           WHERE oi.seller_id = ?
           ORDER BY o.created_at DESC LIMIT 100""",
        (current_user.id, current_user.id),
    )
    return render_template("dashboard/seller/orders.html", orders=orders)


@dashboard_bp.route("/seller/orders/<int:order_id>/verify", methods=["POST"])
@login_required
@role_required("seller", "admin")
def seller_verify_order(order_id):
    """Seller confirms QR payment received → order confirmed + paid."""
    # Ensure this order has an item from this seller
    item = db.fetch_one(
        "SELECT id FROM order_items WHERE order_id = ? AND seller_id = ? LIMIT 1",
        (order_id, current_user.id),
    )
    if not item and current_user.role != "admin":
        flash("Order not found or not yours.", "error")
        return redirect(url_for("dashboard.seller_orders"))
    action = request.form.get("action", "approve").strip()
    order = db.fetch_one("SELECT * FROM orders WHERE id = ?", (order_id,))
    if not order:
        flash("Order not found.", "error")
        return redirect(url_for("dashboard.seller_orders"))
    if action == "approve":
        db.execute(
            """UPDATE orders SET payment_status = 'paid', status = 'confirmed',
               updated_at = datetime('now') WHERE id = ?""",
            (order_id,),
        )
        try:
            db.execute(
                "UPDATE payments SET status = 'verified', verified_at = datetime('now') WHERE order_id = ? AND status = 'pending'",
                (order_id,),
            )
        except Exception:
            pass
        flash(f"Order {order.get('order_id')} payment verified & confirmed.", "success")
    elif action == "reject":
        db.execute(
            """UPDATE orders SET payment_status = 'failed', updated_at = datetime('now') WHERE id = ?""",
            (order_id,),
        )
        flash(f"Order {order.get('order_id')} payment marked failed.", "warning")
    return redirect(url_for("dashboard.seller_orders"))


@dashboard_bp.route("/seller/exchanges")
@login_required
@role_required("seller", "admin")
def seller_exchanges():
    rows = db.fetch_all(
        """SELECT er.*, p.title AS product_title, p.uuid AS product_uuid
           FROM exchange_requests er
           LEFT JOIN products p ON er.desired_product_id = p.id
           WHERE er.lister_id = ? OR p.seller_id = ?
           ORDER BY er.created_at DESC LIMIT 100""",
        (current_user.id, current_user.id),
    )
    return render_template("dashboard/seller/exchanges.html", rows=rows)

@dashboard_bp.route("/seller/exchange/add", methods=["GET", "POST"])
@login_required
@role_required("seller", "admin")
def seller_add_exchange():
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
            return redirect(url_for("dashboard.seller_add_exchange"))
        product_uuid = generate_uuid()
        try:
            db.execute(
                """INSERT INTO products
                   (uuid, seller_id, is_admin_listing, title, brand, model, condition,
                    selling_price, description, location, stock_quantity, payment_method,
                    is_featured, is_active, allows_exchange, exchange_requirements)
                   VALUES (?, ?, 0, ?, ?, ?, ?, 0, ?, ?, 1, 'both', 0, 1, 1, ?)""",
                (product_uuid, current_user.id, title, brand, model, condition,
                 description or requirements, location, requirements),
            )
        except Exception:
            db.execute(
                """INSERT INTO products
                   (uuid, seller_id, is_admin_listing, title, brand, model, condition,
                    selling_price, description, location, stock_quantity, payment_method,
                    is_featured, is_active)
                   VALUES (?, ?, 0, ?, ?, ?, ?, 0, ?, ?, 1, 'both', 0, 1)""",
                (product_uuid, current_user.id, title, brand, model, condition,
                 description or requirements, location),
            )
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
            for i, f in enumerate(request.files.getlist("photos")):
                if f and f.filename:
                    try:
                        result = upload_file_to_cloudinary(f, folder="mobile-clinic/exchange-list")
                        if result and result.get("url"):
                            save_product_image(product_id, result, display_order=i, is_primary=(i == 0))
                    except Exception as e:
                        flash(str(e), "error")
        flash("Exchange listing submitted.", "success")
        return redirect(url_for("dashboard.seller_exchanges"))
    return render_template("dashboard/seller/exchange_form.html")
