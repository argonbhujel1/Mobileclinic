from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import db
from app.utils.helpers import role_required

api_bp = Blueprint("api", __name__)


@api_bp.route("/health")
def health():
    return jsonify({"status": "ok", "service": "Mobile Clinic"})


@api_bp.route("/products/search")
def product_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    rows = db.fetch_all(
        """SELECT uuid, title, brand, model, selling_price,
           (SELECT cloudinary_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC LIMIT 1) AS image
           FROM products p WHERE is_active = 1 AND is_hidden = 0
           AND (title LIKE ? OR brand LIKE ? OR model LIKE ?) LIMIT 10""",
        (f"%{q}%", f"%{q}%", f"%{q}%"),
    )
    return jsonify(rows)


@api_bp.route("/notifications/unread")
@login_required
def unread_notifications():
    count = db.fetch_value(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
        (current_user.id,),
    )
    return jsonify({"count": count or 0})
