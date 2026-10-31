from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import current_user, login_required
from app import db
from app.utils.helpers import generate_order_id, generate_token, format_npr
from app.services.email_service import send_order_confirmation
from app.services.commission_service import create_commission_for_sale
from app.services.image_service import upload_file_to_cloudinary
from app.utils.helpers import generate_uuid
from app.utils.security import hash_password

marketplace_bp = Blueprint("marketplace", __name__)


@marketplace_bp.route("/")
def browse():
    brand = request.args.get("brand", "")
    condition = request.args.get("condition", "")
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "newest")
    page = request.args.get("page", 1, type=int)
    per_page = 12

    sql = """SELECT p.*,
             (SELECT cloudinary_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, display_order LIMIT 1) AS primary_image,
             u.full_name AS seller_name
             FROM products p
             LEFT JOIN users u ON p.seller_id = u.id
             WHERE p.is_active = 1 AND p.is_hidden = 0"""
    params = []
    if brand:
        sql += " AND p.brand = ?"
        params.append(brand)
    if condition:
        sql += " AND p.condition = ?"
        params.append(condition)
    if min_price is not None:
        sql += " AND p.selling_price >= ?"
        params.append(min_price)
    if max_price is not None:
        sql += " AND p.selling_price <= ?"
        params.append(max_price)
    if q:
        sql += " AND (p.title LIKE ? OR p.brand LIKE ? OR p.model LIKE ? OR p.description LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like])

    if sort == "price_asc":
        sql += " ORDER BY p.selling_price ASC"
    elif sort == "price_desc":
        sql += " ORDER BY p.selling_price DESC"
    else:
        sql += " ORDER BY p.is_featured DESC, p.created_at DESC"

    sql += " LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    products = db.fetch_all(sql, tuple(params))
    brands = db.fetch_all("SELECT DISTINCT brand FROM products WHERE is_active = 1 ORDER BY brand")
    return render_template("marketplace/browse.html", products=products, brands=brands, page=page)


@marketplace_bp.route("/exchange")
def exchange_browse():
    """Listings open for exchange."""
    products = db.fetch_all(
        """SELECT p.*,
           (SELECT cloudinary_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, display_order LIMIT 1) AS primary_image
           FROM products p
           WHERE p.is_active = 1 AND p.is_hidden = 0 AND COALESCE(p.allows_exchange, 0) = 1
           ORDER BY p.created_at DESC LIMIT 60"""
    )
    return render_template("marketplace/exchange_browse.html", products=products)


@marketplace_bp.route("/<uuid:product_uuid>/exchange", methods=["GET", "POST"])
def exchange_offer(product_uuid):
    product = db.fetch_one(
        "SELECT * FROM products WHERE uuid = ? AND is_active = 1",
        (str(product_uuid),),
    )
    if not product or not product.get("allows_exchange"):
        flash("This listing is not open for exchange.", "error")
        return redirect(url_for("marketplace.browse"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        mobile = request.form.get("mobile", "").strip()
        brand = request.form.get("offered_brand", "").strip()
        model = request.form.get("offered_model", "").strip()
        condition = request.form.get("offered_condition", "").strip()
        details = request.form.get("offered_details", "").strip()
        cash = request.form.get("cash_difference", type=float) or 0
        if not all([name, mobile, brand, model, details]):
            flash("Name, mobile, brand, model and details are required.", "error")
            return redirect(url_for("marketplace.exchange_offer", product_uuid=product_uuid))

        photo_urls = []
        from app.services.image_service import upload_file_to_cloudinary, import_imgbb_url
        for f in request.files.getlist("photos"):
            if f and f.filename:
                try:
                    result = upload_file_to_cloudinary(f, folder="mobile-clinic/exchange")
                    if result and result.get("url"):
                        photo_urls.append(result["url"])
                except Exception as e:
                    flash(f"Photo upload: {e}", "error")
        imgbb = request.form.get("imgbb_url", "").strip()
        if imgbb:
            try:
                result = import_imgbb_url(imgbb, folder="mobile-clinic/exchange")
                if result and result.get("url"):
                    photo_urls.append(result["url"])
            except Exception as e:
                flash(str(e), "error")

        import json
        cust_id = current_user.id if current_user.is_authenticated else None
        lister_id = product.get("seller_id")
        req_uuid = generate_uuid()
        offered_blob = details
        try:
            db.execute(
                """INSERT INTO exchange_requests
                   (uuid, customer_id, guest_name, guest_email, guest_mobile,
                    offered_phone_details, desired_product_id, cash_difference, status,
                    offer_photos, offered_brand, offered_model, offered_condition, lister_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
                (
                    req_uuid, cust_id, name, email, mobile, offered_blob,
                    product["id"], cash,
                    json.dumps(photo_urls), brand, model, condition, lister_id,
                ),
            )
        except Exception:
            # schema without extra columns
            db.execute(
                """INSERT INTO exchange_requests
                   (uuid, customer_id, guest_name, guest_email, guest_mobile,
                    offered_phone_details, desired_product_id, cash_difference, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                (
                    req_uuid, cust_id, name, email, mobile,
                    f"{brand} {model} ({condition})\n{details}\nPhotos: {', '.join(photo_urls)}",
                    product["id"], cash,
                ),
            )

        # Notify lister + all admins
        title = "New exchange interest"
        msg = f"{name} wants to exchange their {brand} {model} for: {product.get('title')}"
        link = "/admin/exchanges" if not lister_id else "/dashboard/seller/exchanges"
        notify_ids = set()
        if lister_id:
            notify_ids.add(lister_id)
        for a in db.fetch_all("SELECT id FROM users WHERE role = 'admin' AND is_active = 1") or []:
            notify_ids.add(a["id"])
        for uid in notify_ids:
            try:
                db.execute(
                    "INSERT INTO notifications (user_id, title, message, link) VALUES (?, ?, ?, ?)",
                    (uid, title, msg, link),
                )
            except Exception:
                pass

        flash("Exchange interest submitted. The seller and admin have been notified.", "success")
        return redirect(url_for("marketplace.detail", product_uuid=product_uuid))

    return render_template("marketplace/exchange_offer.html", product=product)



@marketplace_bp.route("/<uuid>")
def detail(uuid):
    product = db.fetch_one(
        """SELECT p.*, u.full_name AS seller_name, u.uuid AS seller_uuid,
              u.profile_photo_url AS seller_photo, u.bio AS seller_bio, u.shop_name AS seller_shop
           FROM products p LEFT JOIN users u ON p.seller_id = u.id
           WHERE p.uuid = ? AND p.is_active = 1 AND p.is_hidden = 0""",
        (uuid,),
    )
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("marketplace.browse"))
    images = db.fetch_all(
        "SELECT * FROM product_images WHERE product_id = ? ORDER BY is_primary DESC, display_order",
        (product["id"],),
    )
    # Hide IMEI from public
    product.pop("imei_serial", None)
    related = db.fetch_all(
        """SELECT p.*, (SELECT cloudinary_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC LIMIT 1) AS primary_image
           FROM products p WHERE p.brand = ? AND p.id != ? AND p.is_active = 1 AND p.is_hidden = 0 LIMIT 4""",
        (product["brand"], product["id"]),
    )
    db.execute("UPDATE products SET views_count = views_count + 1 WHERE id = ?", (product["id"],))
    return render_template("marketplace/detail.html", product=product, images=images, related=related)


@marketplace_bp.route("/seller/<seller_uuid>")
def seller_profile(seller_uuid):
    seller = db.fetch_one(
        """SELECT id, uuid, full_name, profile_photo_url, bio, shop_name, mobile, address, created_at
           FROM users WHERE uuid = ? AND role IN ('seller','admin')""",
        (seller_uuid,),
    )
    if not seller:
        flash("Seller not found.", "error")
        return redirect(url_for("marketplace.browse"))
    products = db.fetch_all(
        """SELECT p.*, (SELECT cloudinary_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC LIMIT 1) AS primary_image
           FROM products p WHERE p.seller_id = ? AND p.is_active = 1 AND p.is_hidden = 0 ORDER BY p.created_at DESC""",
        (seller["id"],),
    )
    return render_template("marketplace/seller_profile.html", seller=seller, products=products)


@marketplace_bp.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if current_user.role not in ("seller", "admin"):
        flash("You need a seller account to list phones. Apply from your dashboard.", "info")
        return redirect(url_for("dashboard.customer"))
    if request.method == "POST":
        # Product creation handled via form + image uploads (see API / dashboard)
        flash("Use the Seller Dashboard → Add Phone for full listing with photos.", "info")
        return redirect(url_for("dashboard.seller_add_phone"))
    return render_template("marketplace/sell.html")


@marketplace_bp.route("/cart")
def cart():
    cart = session.get("cart", {})
    items = []
    total = 0
    for pid, qty in cart.items():
        p = db.fetch_one(
            """SELECT p.*, (SELECT cloudinary_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC LIMIT 1) AS primary_image
               FROM products p WHERE p.id = ? AND p.is_active = 1""",
            (int(pid),),
        )
        if p:
            p["qty"] = qty
            p["subtotal"] = p["selling_price"] * qty
            total += p["subtotal"]
            items.append(p)
    return render_template("marketplace/cart.html", items=items, total=total)


@marketplace_bp.route("/cart/add/<int:product_id>", methods=["POST"])
def cart_add(product_id):
    product = db.fetch_one("SELECT id, stock_quantity FROM products WHERE id = ? AND is_active = 1", (product_id,))
    if not product or product["stock_quantity"] < 1:
        flash("Product unavailable.", "error")
        return redirect(request.referrer or url_for("marketplace.browse"))
    cart = session.get("cart", {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session["cart"] = cart
    session.modified = True
    flash("Added to cart.", "success")
    return redirect(request.referrer or url_for("marketplace.cart"))

@marketplace_bp.route("/cart/clear", methods=["POST"])
def cart_clear():
    session.pop("cart", None)
    session.modified = True
    flash("Cart cleared.", "success")
    return redirect(url_for("marketplace.cart"))


@marketplace_bp.route("/cart/remove/<int:product_id>", methods=["POST"])
def cart_remove(product_id):
    cart = session.get("cart", {})
    cart.pop(str(product_id), None)
    session["cart"] = cart
    session.modified = True
    flash("Item removed from cart.", "success")
    return redirect(url_for("marketplace.cart"))


@marketplace_bp.route("/cart/update/<int:product_id>", methods=["POST"])
def cart_update(product_id):
    qty = request.form.get("qty", type=int) or 0
    cart = session.get("cart", {})
    if qty <= 0:
        cart.pop(str(product_id), None)
    else:
        cart[str(product_id)] = qty
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("marketplace.cart"))




@marketplace_bp.route("/buy-now/<int:product_id>", methods=["POST"])
def buy_now(product_id):
    """Add product to cart and go straight to checkout."""
    product = db.fetch_one("SELECT id, stock_quantity FROM products WHERE id = ? AND is_active = 1", (product_id,))
    if not product or product["stock_quantity"] < 1:
        flash("Product unavailable.", "error")
        return redirect(request.referrer or url_for("marketplace.browse"))
    cart = session.get("cart", {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("marketplace.checkout"))



@marketplace_bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = session.get("cart", {})
    if not cart:
        flash("Your cart is empty.", "info")
        return redirect(url_for("marketplace.browse"))
    items = []
    total = 0
    min_qr_total = 0
    for pid, qty in cart.items():
        p = db.fetch_one("SELECT * FROM products WHERE id = ? AND is_active = 1", (int(pid),))
        if p and p["stock_quantity"] >= qty:
            p["qty"] = qty
            p["subtotal"] = p["selling_price"] * qty
            # Per-unit min QR; default full price if not set
            unit_min = p.get("min_qr_amount")
            if unit_min is None or unit_min == "":
                unit_min = p["selling_price"]
            try:
                unit_min = float(unit_min)
            except (TypeError, ValueError):
                unit_min = float(p["selling_price"] or 0)
            p["min_qr_line"] = unit_min * qty
            min_qr_total += p["min_qr_line"]
            total += p["subtotal"]
            items.append(p)
    if not items:
        flash("No valid items in cart.", "error")
        return redirect(url_for("marketplace.cart"))

    # QR for payment: prefer seller QR if all cart items are from the same seller
    payment_qr = None
    payment_qr_label = "Admin payment QR"
    seller_ids = set()
    for p in items:
        if p.get("is_admin_listing"):
            seller_ids.add("admin")
        elif p.get("seller_id"):
            seller_ids.add(p["seller_id"])
    if len(seller_ids) == 1:
        only = next(iter(seller_ids))
        if only != "admin":
            seller = db.fetch_one(
                "SELECT full_name, shop_name, seller_qr_url FROM users WHERE id = ?",
                (only,),
            )
            if seller and seller.get("seller_qr_url"):
                payment_qr = {
                    "cloudinary_url": seller["seller_qr_url"],
                    "label": (seller.get("shop_name") or seller.get("full_name") or "Seller") + " QR",
                }
                payment_qr_label = payment_qr["label"]
    if not payment_qr:
        admin_qr_row = db.fetch_one(
            "SELECT * FROM admin_qr_codes WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
        )
        if admin_qr_row:
            payment_qr = admin_qr_row
            payment_qr_label = admin_qr_row.get("label") or "Admin payment QR"
    admin_qr = payment_qr  # template still uses admin_qr

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip().lower()
        address = request.form.get("address", "").strip()
        payment_method = request.form.get("payment_method", "cod")
        if not all([name, mobile, email, address]):
            flash("All fields are required.", "error")
            return render_template(
                "marketplace/checkout.html",
                items=items,
                total=total,
                min_qr_total=min_qr_total,
                admin_qr=admin_qr,
            )

        payment_status = "cod" if payment_method == "cod" else "pending"
        payment_reference = None
        payment_amount_claimed = None
        payment_proof_url = None
        order_status = "pending"

        if payment_method == "qr":
            if not admin_qr:
                flash("QR payment is not available right now. Please use COD or try later.", "error")
                return render_template(
                    "marketplace/checkout.html",
                    items=items,
                    total=total,
                    min_qr_total=min_qr_total,
                    admin_qr=admin_qr,
                )
            paid_raw = request.form.get("qr_paid_amount", "").strip()
            payment_reference = request.form.get("qr_reference", "").strip()
            try:
                payment_amount_claimed = float(paid_raw) if paid_raw else 0
            except ValueError:
                payment_amount_claimed = 0
            if payment_amount_claimed < min_qr_total:
                flash(
                    f"QR payment must be at least NPR {min_qr_total:,.0f} (minimum set by admin). You entered NPR {payment_amount_claimed:,.0f}.",
                    "error",
                )
                return render_template(
                    "marketplace/checkout.html",
                    items=items,
                    total=total,
                    min_qr_total=min_qr_total,
                    admin_qr=admin_qr,
                )
            if not payment_reference:
                flash("Enter your QR payment transaction / reference ID.", "error")
                return render_template(
                    "marketplace/checkout.html",
                    items=items,
                    total=total,
                    min_qr_total=min_qr_total,
                    admin_qr=admin_qr,
                )
            # Optional receipt upload
            if "qr_receipt" in request.files and request.files["qr_receipt"].filename:
                try:
                    result = upload_file_to_cloudinary(
                        request.files["qr_receipt"], folder="mobile-clinic/payment-proofs"
                    )
                    if result:
                        payment_proof_url = result.get("url")
                except Exception as e:
                    flash(f"Receipt upload failed: {e}", "warning")
            payment_status = "awaiting_verification"
            order_status = "pending"  # confirmed only after admin verifies payment

        order_id = generate_order_id()
        tracking_token = generate_token(24)
        user_id = current_user.id if current_user.is_authenticated else None

        # Try extended columns; fallback if migration not applied
        try:
            db.execute(
                """INSERT INTO orders (order_id, user_id, guest_name, guest_email, guest_mobile, delivery_address,
                   payment_method, payment_status, total_amount, status, tracking_token,
                   payment_reference, payment_amount_claimed, payment_proof_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order_id, user_id, name, email, mobile, address, payment_method,
                    payment_status, total, order_status, tracking_token,
                    payment_reference, payment_amount_claimed, payment_proof_url,
                ),
            )
        except Exception:
            db.execute(
                """INSERT INTO orders (order_id, user_id, guest_name, guest_email, guest_mobile, delivery_address,
                   payment_method, payment_status, total_amount, status, tracking_token)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order_id, user_id, name, email, mobile, address, payment_method,
                    payment_status, total, order_status, tracking_token,
                ),
            )

        row = db.fetch_one("SELECT id FROM orders WHERE order_id = ?", (order_id,))
        oid = row["id"] if row else None
        if not oid:
            flash("Order could not be created. Please try again.", "error")
            return render_template(
                "marketplace/checkout.html",
                items=items,
                total=total,
                min_qr_total=min_qr_total,
                admin_qr=admin_qr,
            )

        order_items_data = []
        for p in items:
            is_admin = 1 if p.get("is_admin_listing") else 0
            seller_id = p.get("seller_id")
            commission_rate = current_app.config["COMMISSION_RATE"] if seller_id and not is_admin else 0
            commission_amt = round(p["subtotal"] * commission_rate, 2) if commission_rate else 0
            db.execute(
                """INSERT INTO order_items (order_id, product_id, product_title, product_price, quantity,
                   is_admin_listing, seller_id, commission_rate, commission_amount)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (oid, p["id"], p["title"], p["selling_price"], p["qty"], is_admin, seller_id, commission_rate, commission_amt),
            )
            item_row = db.fetch_one(
                "SELECT id FROM order_items WHERE order_id = ? AND product_id = ? ORDER BY id DESC LIMIT 1",
                (oid, p["id"]),
            )
            item_id = item_row["id"] if item_row else None
            db.execute(
                "UPDATE products SET stock_quantity = stock_quantity - ? WHERE id = ?",
                (p["qty"], p["id"]),
            )
            if item_id and seller_id and not is_admin and commission_amt > 0:
                create_commission_for_sale(item_id, oid, seller_id, p["subtotal"])
            order_items_data.append({"title": p["title"], "price": p["selling_price"], "qty": p["qty"]})

        # payments table record for QR
        if payment_method == "qr":
            try:
                db.execute(
                    """INSERT INTO payments (uuid, order_id, user_id, amount, method, status, reference_id, receipt_url, notes)
                       VALUES (?, ?, ?, ?, 'qr', 'pending', ?, ?, ?)""",
                    (
                        generate_uuid(),
                        oid,
                        user_id,
                        payment_amount_claimed,
                        payment_reference,
                        payment_proof_url,
                        f"Min required NPR {min_qr_total:,.0f}",
                    ),
                )
            except Exception:
                pass

        session.pop("cart", None)
        tracking_url = f"{current_app.config['APP_BASE_URL']}/phones/track/{order_id}?token={tracking_token}"
        order = {
            "order_id": order_id,
            "guest_email": email,
            "guest_name": name,
            "total_amount": total,
            "payment_method": payment_method,
        }
        try:
            send_order_confirmation(order, order_items_data, tracking_url)
        except Exception:
            pass
        if payment_method == "qr":
            flash(
                f"Order submitted! Order ID: {order_id}. QR payment NPR {payment_amount_claimed:,.0f} is awaiting admin verification.",
                "success",
            )
        else:
            flash(f"Order placed successfully! Order ID: {order_id}", "success")
        return redirect(url_for("marketplace.track", order_id=order_id, token=tracking_token))

    return render_template(
        "marketplace/checkout.html",
        items=items,
        total=total,
        min_qr_total=min_qr_total,
        admin_qr=admin_qr,
    )


@marketplace_bp.route("/track/<order_id>")
def track(order_id):
    token = request.args.get("token", "")
    order = db.fetch_one("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    if not order:
        flash("Order not found.", "error")
        return redirect(url_for("main.home"))
    # Secure: require token or logged-in owner
    if order["tracking_token"] != token:
        if not current_user.is_authenticated or (order["user_id"] and order["user_id"] != current_user.id):
            flash("Invalid tracking credentials.", "error")
            return redirect(url_for("main.home"))
    items = db.fetch_all("SELECT * FROM order_items WHERE order_id = ?", (order["id"],))
    return render_template("marketplace/track.html", order=order, items=items)
