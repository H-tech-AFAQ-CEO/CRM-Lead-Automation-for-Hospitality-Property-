from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import models

app = Flask(__name__, template_folder="templates")
CORS(app)


# ── Static ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Leads ──────────────────────────────────────────────────────────────────

@app.route("/api/leads", methods=["GET"])
def list_leads():
    leads = models.get_all_leads()
    stage = request.args.get("stage")
    source = request.args.get("source")
    q = request.args.get("q", "").lower()
    if stage:
        leads = [l for l in leads if l.get("stage") == stage]
    if source:
        leads = [l for l in leads if l.get("source") == source]
    if q:
        leads = [
            l for l in leads
            if q in l.get("name", "").lower()
            or q in l.get("email", "").lower()
            or q in l.get("message", "").lower()
        ]
    leads.sort(key=lambda l: l.get("updated_at", ""), reverse=True)
    return jsonify(leads)


@app.route("/api/leads", methods=["POST"])
def create_lead():
    payload = request.get_json(force=True)
    if not payload.get("name"):
        return jsonify({"error": "name is required"}), 400
    lead = models.create_lead(payload)
    return jsonify(lead), 201


@app.route("/api/leads/<lead_id>", methods=["GET"])
def get_lead(lead_id):
    lead = models.get_lead(lead_id)
    if not lead:
        return jsonify({"error": "not found"}), 404
    return jsonify(lead)


@app.route("/api/leads/<lead_id>", methods=["PATCH"])
def update_lead(lead_id):
    payload = request.get_json(force=True)
    lead = models.update_lead(lead_id, payload)
    if not lead:
        return jsonify({"error": "not found"}), 404
    return jsonify(lead)


@app.route("/api/leads/<lead_id>", methods=["DELETE"])
def delete_lead(lead_id):
    ok = models.delete_lead(lead_id)
    if not ok:
        return jsonify({"error": "not found"}), 404
    return jsonify({"deleted": True})


@app.route("/api/leads/<lead_id>/messages", methods=["POST"])
def add_message(lead_id):
    payload = request.get_json(force=True)
    direction = payload.get("direction", "outbound")
    channel = payload.get("channel", "Email")
    body = payload.get("body", "")
    if not body:
        return jsonify({"error": "body required"}), 400
    msg = models.add_message_to_lead(lead_id, direction, channel, body)
    if not msg:
        return jsonify({"error": "lead not found"}), 404
    return jsonify(msg), 201


# ── Meta ───────────────────────────────────────────────────────────────────

@app.route("/api/meta", methods=["GET"])
def meta():
    return jsonify({
        "stages": models.LEAD_STAGES,
        "sources": models.SOURCES,
        "lost_reasons": models.LOST_REASONS,
        "won_reasons": models.WON_REASONS,
        "checkin_stages": models.CHECKIN_STAGES,
    })


# ── Stats ──────────────────────────────────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
def stats():
    return jsonify(models.get_stats())


# ── Notifications ──────────────────────────────────────────────────────────

@app.route("/api/notifications", methods=["GET"])
def notifications():
    return jsonify(models.get_notifications())


@app.route("/api/notifications/read", methods=["POST"])
def mark_read():
    models.mark_notifications_read()
    return jsonify({"ok": True})


# ── Intake (simulated multi-channel) ──────────────────────────────────────

@app.route("/api/intake/email", methods=["POST"])
def intake_email():
    """Simulate receiving a raw email inquiry."""
    payload = request.get_json(force=True)
    lead = models.create_lead({
        "name": payload.get("from_name", "Unknown"),
        "email": payload.get("from_email", ""),
        "source": "Email",
        "message": payload.get("body", ""),
        "notes": f"Subject: {payload.get('subject', '')}",
    })
    return jsonify({"status": "received", "lead_id": lead["id"]}), 201


@app.route("/api/intake/whatsapp", methods=["POST"])
def intake_whatsapp():
    """Simulate receiving a WhatsApp message."""
    payload = request.get_json(force=True)
    phone = payload.get("from", "")
    existing = next(
        (l for l in models.get_all_leads() if l.get("phone") == phone), None
    )
    if existing:
        msg = models.add_message_to_lead(
            existing["id"], "inbound", "WhatsApp", payload.get("body", "")
        )
        return jsonify({"status": "appended", "lead_id": existing["id"], "message": msg})
    lead = models.create_lead({
        "name": payload.get("name", phone),
        "phone": phone,
        "source": "WhatsApp",
        "message": payload.get("body", ""),
    })
    return jsonify({"status": "created", "lead_id": lead["id"]}), 201


@app.route("/api/intake/instagram", methods=["POST"])
def intake_instagram():
    """Simulate receiving an Instagram DM."""
    payload = request.get_json(force=True)
    lead = models.create_lead({
        "name": payload.get("username", "Unknown"),
        "source": "Instagram",
        "message": payload.get("body", ""),
    })
    return jsonify({"status": "received", "lead_id": lead["id"]}), 201


if __name__ == "__main__":
    app.run(debug=True, port=5000)