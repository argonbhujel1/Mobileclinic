from flask import Blueprint, render_template, request, current_app, flash, redirect, url_for, make_response, Response, make_response
from app import db
from datetime import datetime

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    featured = db.fetch_all(
        """SELECT p.*, 
           (SELECT cloudinary_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, display_order LIMIT 1) AS primary_image
           FROM products p
           WHERE p.is_active = 1 AND p.is_hidden = 0 AND p.is_featured = 1
           ORDER BY p.created_at DESC LIMIT 8"""
    )
    latest = db.fetch_all(
        """SELECT p.*,
           (SELECT cloudinary_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, display_order LIMIT 1) AS primary_image
           FROM products p
           WHERE p.is_active = 1 AND p.is_hidden = 0 AND p.is_featured = 0
           ORDER BY p.created_at DESC LIMIT 12"""
    )
    brands = db.fetch_all(
        "SELECT DISTINCT brand FROM products WHERE is_active = 1 AND is_hidden = 0 ORDER BY brand LIMIT 12"
    )
    return render_template(
        "pages/home.html",
        featured=featured,
        latest=latest,
        brands=brands,
    )


@main_bp.route("/about")
def about():
    return render_template("pages/about.html")


@main_bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        # Simple contact form handling
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()
        # In production, send email to admin
        from flask import flash, redirect, url_for
        flash("Thank you! We will get back to you soon.", "success")
        return redirect(url_for("main.contact"))
    return render_template("pages/contact.html")


@main_bp.route("/faq")
def faq():
    return render_template("pages/faq.html")


@main_bp.route("/privacy")
def privacy():
    return render_template("pages/privacy.html")


@main_bp.route("/terms")
def terms():
    return render_template("pages/terms.html")


@main_bp.route("/refund-policy")
def refund():
    return render_template("pages/refund.html")


@main_bp.route("/buy-sell-exchange")
def buy_sell_exchange():
    return render_template("pages/buy_sell_exchange.html")


@main_bp.route("/track", methods=["GET", "POST"])
def track_lookup():
    """Public track: find orders & repairs by name + mobile + email (no order number required)."""
    results = {"orders": [], "repairs": []}
    searched = False
    form = {"name": "", "mobile": "", "email": ""}
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip().lower()
        form = {"name": name, "mobile": mobile, "email": email}
        searched = True
        if not mobile and not email:
            flash("Enter at least mobile number or email.", "error")
        else:
            # Orders: match guest fields and/or linked user
            order_sql = """SELECT * FROM orders WHERE 1=1"""
            order_params = []
            clauses = []
            if mobile:
                clauses.append("(guest_mobile = ? OR guest_mobile LIKE ?)")
                order_params.extend([mobile, f"%{mobile[-10:]}"])
            if email:
                clauses.append("LOWER(guest_email) = ?")
                order_params.append(email)
            if name:
                clauses.append("LOWER(guest_name) LIKE ?")
                order_params.append(f"%{name.lower()}%")
            if clauses:
                order_sql += " AND (" + " OR ".join(clauses) + ")"
            order_sql += " ORDER BY created_at DESC LIMIT 20"
            results["orders"] = db.fetch_all(order_sql, tuple(order_params)) if order_params else []

            # Also match by registered user email/mobile
            if email or mobile:
                user_clauses = []
                user_params = []
                if email:
                    user_clauses.append("LOWER(email) = ?")
                    user_params.append(email)
                if mobile:
                    user_clauses.append("mobile = ? OR mobile LIKE ?")
                    user_params.extend([mobile, f"%{mobile[-10:]}"])
                users = db.fetch_all(
                    "SELECT id FROM users WHERE " + " OR ".join(user_clauses),
                    tuple(user_params),
                )
                for u in users:
                    extra = db.fetch_all(
                        "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
                        (u["id"],),
                    )
                    seen = {o["id"] for o in results["orders"]}
                    for o in extra:
                        if o["id"] not in seen:
                            results["orders"].append(o)

            # Repairs
            repair_sql = "SELECT * FROM repair_tickets WHERE 1=1"
            repair_params = []
            r_clauses = []
            if mobile:
                r_clauses.append("(guest_mobile = ? OR guest_mobile LIKE ?)")
                repair_params.extend([mobile, f"%{mobile[-10:]}"])
            if email:
                r_clauses.append("LOWER(guest_email) = ?")
                repair_params.append(email)
            if name:
                r_clauses.append("LOWER(guest_name) LIKE ?")
                repair_params.append(f"%{name.lower()}%")
            if r_clauses:
                repair_sql += " AND (" + " OR ".join(r_clauses) + ")"
            repair_sql += " ORDER BY created_at DESC LIMIT 20"
            results["repairs"] = db.fetch_all(repair_sql, tuple(repair_params)) if repair_params else []

            if email or mobile:
                users = db.fetch_all(
                    "SELECT id FROM users WHERE " + (
                        " OR ".join(
                            (["LOWER(email) = ?"] if email else [])
                            + (["mobile = ? OR mobile LIKE ?"] if mobile else [])
                        )
                    ),
                    tuple(
                        ([email] if email else [])
                        + ([mobile, f"%{mobile[-10:]}"] if mobile else [])
                    ),
                )
                for u in users:
                    extra = db.fetch_all(
                        "SELECT * FROM repair_tickets WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
                        (u["id"],),
                    )
                    seen = {r["id"] for r in results["repairs"]}
                    for r in extra:
                        if r["id"] not in seen:
                            results["repairs"].append(r)

            if not results["orders"] and not results["repairs"]:
                flash("No orders or repairs found for those details.", "info")

    return render_template("pages/track.html", results=results, searched=searched, form=form)

@main_bp.route("/robots.txt")
def robots_txt():
    base = (current_app.config.get("APP_BASE_URL") or request.url_root or "").rstrip("/")
    lines = [
        "User-agent: *",
        "Allow: /",
        "Allow: /phones",
        "Allow: /phones/",
        "Allow: /repair",
        "Allow: /about",
        "Allow: /contact",
        "Allow: /faq",
        "Allow: /buy-sell-exchange",
        "",
        "Disallow: /admin",
        "Disallow: /admin/",
        "Disallow: /dashboard",
        "Disallow: /dashboard/",
        "Disallow: /auth/login",
        "Disallow: /auth/register",
        "Disallow: /api/",
        "",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ]
    resp = make_response("\n".join(lines))
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    return resp


@main_bp.route("/sitemap.xml")
def sitemap_xml():
    base = (current_app.config.get("APP_BASE_URL") or request.url_root or "").rstrip("/")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    static_urls = [
        ("/", "1.0", "daily"),
        ("/phones/", "0.9", "daily"),
        ("/repair", "0.8", "weekly"),
        ("/repair/book", "0.7", "weekly"),
        ("/about", "0.6", "monthly"),
        ("/contact", "0.6", "monthly"),
        ("/faq", "0.5", "monthly"),
        ("/buy-sell-exchange", "0.7", "weekly"),
        ("/track", "0.4", "monthly"),
        ("/privacy", "0.3", "yearly"),
        ("/terms", "0.3", "yearly"),
    ]
    try:
        products = db.fetch_all(
            "SELECT uuid, updated_at, created_at FROM products "
            "WHERE is_active = 1 AND is_hidden = 0 ORDER BY updated_at DESC LIMIT 500"
        ) or []
    except Exception:
        products = []
    try:
        sellers = db.fetch_all(
            "SELECT uuid FROM users WHERE role IN ('seller','admin') AND is_active = 1 LIMIT 100"
        ) or []
    except Exception:
        sellers = []

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, prio, freq in static_urls:
        parts.extend([
            "  <url>",
            f"    <loc>{base}{path}</loc>",
            f"    <lastmod>{today}</lastmod>",
            f"    <changefreq>{freq}</changefreq>",
            f"    <priority>{prio}</priority>",
            "  </url>",
        ])
    for row in products:
        uuid = row.get("uuid")
        if not uuid:
            continue
        lm = row.get("updated_at") or row.get("created_at") or today
        if hasattr(lm, "strftime"):
            lm = lm.strftime("%Y-%m-%d")
        else:
            lm = str(lm)[:10]
        parts.extend([
            "  <url>",
            f"    <loc>{base}/phones/{uuid}</loc>",
            f"    <lastmod>{lm}</lastmod>",
            "    <changefreq>weekly</changefreq>",
            "    <priority>0.8</priority>",
            "  </url>",
        ])
    for row in sellers:
        uuid = row.get("uuid")
        if not uuid:
            continue
        parts.extend([
            "  <url>",
            f"    <loc>{base}/phones/seller/{uuid}</loc>",
            f"    <lastmod>{today}</lastmod>",
            "    <changefreq>weekly</changefreq>",
            "    <priority>0.5</priority>",
            "  </url>",
        ])
    parts.append("</urlset>")
    resp = make_response("\n".join(parts))
    resp.headers["Content-Type"] = "application/xml; charset=utf-8"
    return resp
