from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import current_user, login_required
from app import db
from app.extensions import csrf
from app.utils.helpers import generate_ticket_id, generate_token, now_kathmandu
from app.services.email_service import send_repair_confirmation
from app.utils.helpers import role_required

repair_bp = Blueprint("repair", __name__)


@repair_bp.route("/")
def services():
    return render_template("repair/services.html")


@repair_bp.route("/book", methods=["GET", "POST"])
def book():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip().lower()
        brand = request.form.get("phone_brand", "").strip()
        model = request.form.get("phone_model", "").strip()
        problem = request.form.get("problem_description", "").strip()
        address = request.form.get("pickup_address", "").strip()
        lat = request.form.get("pickup_latitude", type=float)
        lng = request.form.get("pickup_longitude", type=float)
        instructions = request.form.get("pickup_instructions", "").strip()

        if not all([name, mobile, email, brand, model, problem, address]):
            flash("Please fill all required fields.", "error")
            return render_template("repair/book.html")

        ticket_id = generate_ticket_id()
        tracking_token = generate_token(24)
        user_id = current_user.id if current_user.is_authenticated else None

        db.execute(
            """INSERT INTO repair_tickets
               (ticket_id, user_id, guest_name, guest_email, guest_mobile, phone_brand, phone_model,
                problem_description, pickup_address, pickup_latitude, pickup_longitude, pickup_instructions,
                status, tracking_token)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?)""",
            (ticket_id, user_id, name, email, mobile, brand, model, problem, address, lat, lng, instructions, tracking_token),
        )
        row = db.fetch_one("SELECT id FROM repair_tickets WHERE ticket_id = ?", (ticket_id,))
        tid = row["id"] if row else None
        if tid:
            db.execute(
                "INSERT INTO repair_status_history (repair_ticket_id, status, notes) VALUES (?, 'submitted', 'Repair request submitted')",
                (tid,),
            )

        tracking_url = f"{current_app.config['APP_BASE_URL']}/repair/track/{ticket_id}?token={tracking_token}"
        ticket = {"ticket_id": ticket_id, "guest_email": email, "guest_name": name, "phone_brand": brand, "phone_model": model}
        send_repair_confirmation(ticket, tracking_url)
        flash(f"Repair booked! Ticket ID: {ticket_id}. Check your email for tracking link.", "success")
        return redirect(url_for("repair.track", ticket_id=ticket_id, token=tracking_token))

    return render_template("repair/book.html")


@repair_bp.route("/track/<ticket_id>")
def track(ticket_id):
    token = request.args.get("token", "")
    ticket = db.fetch_one("SELECT * FROM repair_tickets WHERE ticket_id = ?", (ticket_id,))
    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for("repair.services"))
    allowed = False
    if token and ticket.get("tracking_token") == token:
        allowed = True
    elif current_user.is_authenticated:
        if ticket.get("user_id") and ticket["user_id"] == current_user.id:
            allowed = True
        elif getattr(current_user, "role", None) == "admin":
            allowed = True
        elif ticket.get("guest_email") and current_user.email and ticket["guest_email"].lower() == current_user.email.lower():
            allowed = True
    if not allowed:
        flash("Invalid tracking credentials. Use Track page with your mobile/email, or open the link from your email.", "error")
        return redirect(url_for("main.track_lookup"))

    history = db.fetch_all(
        "SELECT * FROM repair_status_history WHERE repair_ticket_id = ? ORDER BY created_at",
        (ticket["id"],),
    )
    # Active trip location
    trip = db.fetch_one(
        """SELECT t.*, 
           (SELECT latitude FROM trip_location_updates WHERE trip_id = t.id ORDER BY recorded_at DESC LIMIT 1) AS last_lat,
           (SELECT longitude FROM trip_location_updates WHERE trip_id = t.id ORDER BY recorded_at DESC LIMIT 1) AS last_lng,
           (SELECT recorded_at FROM trip_location_updates WHERE trip_id = t.id ORDER BY recorded_at DESC LIMIT 1) AS last_update
           FROM trips t WHERE t.repair_ticket_id = ? AND t.status IN ('started','in_progress')
           ORDER BY t.created_at DESC LIMIT 1""",
        (ticket["id"],),
    )
    return render_template("repair/track.html", ticket=ticket, history=history, trip=trip)


@repair_bp.route("/api/location-update", methods=["POST"])
@login_required
@csrf.exempt
def location_update():
    """Admin/staff shares GPS while on pickup or delivery trip."""
    if getattr(current_user, "role", None) not in ("admin", "staff"):
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json(silent=True) or {}
    trip_key = data.get("trip_id") or data.get("trip_uuid")
    lat = data.get("latitude")
    lng = data.get("longitude")
    accuracy = data.get("accuracy")
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid coordinates"}), 400
    if not trip_key:
        return jsonify({"error": "Missing trip_id"}), 400

    trip = db.fetch_one(
        "SELECT * FROM trips WHERE (uuid = ? OR id = ?) AND staff_id = ?",
        (str(trip_key), trip_key if str(trip_key).isdigit() else -1, current_user.id),
    )
    if not trip:
        # admin can update any active trip they own; also try by uuid only for admin
        if current_user.role == "admin":
            trip = db.fetch_one(
                "SELECT * FROM trips WHERE uuid = ? OR id = ?",
                (str(trip_key), trip_key if str(trip_key).isdigit() else -1),
            )
    if not trip or trip["status"] not in ("started", "in_progress"):
        return jsonify({"error": "Invalid or inactive trip"}), 400

    db.execute(
        """INSERT INTO trip_location_updates (trip_id, staff_id, latitude, longitude, accuracy)
           VALUES (?, ?, ?, ?, ?)""",
        (trip["id"], current_user.id, lat, lng, accuracy),
    )
    if trip["status"] == "started":
        db.execute("UPDATE trips SET status = 'in_progress' WHERE id = ?", (trip["id"],))
    return jsonify({"ok": True, "trip_uuid": trip["uuid"]})


@repair_bp.route("/api/track/<ticket_id>")
def track_api(ticket_id):
    """JSON location for customer/admin map polling (token or owner)."""
    token = request.args.get("token", "")
    ticket = db.fetch_one("SELECT * FROM repair_tickets WHERE ticket_id = ?", (ticket_id,))
    if not ticket:
        return jsonify({"error": "Not found"}), 404
    allowed = False
    if token and ticket.get("tracking_token") == token:
        allowed = True
    elif current_user.is_authenticated:
        if ticket.get("user_id") and ticket["user_id"] == current_user.id:
            allowed = True
        elif getattr(current_user, "role", None) == "admin":
            allowed = True
    if not allowed:
        return jsonify({"error": "Unauthorized"}), 403

    trip = db.fetch_one(
        """SELECT t.*,
           (SELECT latitude FROM trip_location_updates WHERE trip_id = t.id ORDER BY recorded_at DESC LIMIT 1) AS last_lat,
           (SELECT longitude FROM trip_location_updates WHERE trip_id = t.id ORDER BY recorded_at DESC LIMIT 1) AS last_lng,
           (SELECT recorded_at FROM trip_location_updates WHERE trip_id = t.id ORDER BY recorded_at DESC LIMIT 1) AS last_update
           FROM trips t WHERE t.repair_ticket_id = ? AND t.status IN ('started','in_progress')
           ORDER BY t.created_at DESC LIMIT 1""",
        (ticket["id"],),
    )
    return jsonify({
        "ticket_id": ticket["ticket_id"],
        "status": ticket["status"],
        "pickup_lat": ticket.get("pickup_latitude"),
        "pickup_lng": ticket.get("pickup_longitude"),
        "pickup_address": ticket.get("pickup_address"),
        "trip": {
            "uuid": trip["uuid"],
            "type": trip["trip_type"],
            "status": trip["status"],
            "last_lat": trip["last_lat"],
            "last_lng": trip["last_lng"],
            "last_update": trip["last_update"],
            "destination_lat": trip.get("destination_lat"),
            "destination_lng": trip.get("destination_lng"),
        } if trip else None,
    })
