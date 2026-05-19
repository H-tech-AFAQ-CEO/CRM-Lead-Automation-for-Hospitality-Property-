import sqlite3
import uuid
import os
from datetime import datetime

DB_FILE = "crm.db"

LEAD_STAGES = ["New", "Replied", "Qualified", "Quoted", "Won", "Lost"]
LOST_REASONS = ["Budget", "Booked Elsewhere", "No Reply", "Dates Unavailable", "Other"]
WON_REASONS = ["Value", "Location", "Referral", "Reviews", "Other"]
SOURCES = ["Email", "Instagram", "WhatsApp", "Platform Forward", "Direct Message", "Other"]
CHECKIN_STAGES = ["ID Requested", "ID Received", "Approved", "Ready for Arrival"]


def _get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    if not os.path.exists(DB_FILE):
        conn = _get_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                source TEXT DEFAULT 'Other',
                stage TEXT DEFAULT 'New',
                notes TEXT,
                event_date TEXT,
                guest_count INTEGER,
                message TEXT,
                win_loss TEXT,
                checkin_status TEXT DEFAULT 'ID Requested',
                brochure_sent INTEGER DEFAULT 0,
                auto_reply_sent INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                lead_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                channel TEXT NOT NULL,
                body TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                message TEXT NOT NULL,
                lead_id TEXT,
                read INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()


_init_db()


def _row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    if d.get("messages"):
        try:
            d["messages"] = []
        except:
            pass
    return d


def get_all_leads():
    conn = _get_db()
    cursor = conn.execute("SELECT * FROM leads ORDER BY updated_at DESC")
    leads = [_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    for lead in leads:
        lead["messages"] = get_messages_for_lead(lead["id"])
    return leads


def get_lead(lead_id):
    conn = _get_db()
    cursor = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        lead = _row_to_dict(row)
        lead["messages"] = get_messages_for_lead(lead_id)
        return lead
    return None


def get_messages_for_lead(lead_id):
    conn = _get_db()
    cursor = conn.execute("SELECT * FROM messages WHERE lead_id = ? ORDER BY timestamp ASC", (lead_id,))
    msgs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return msgs


def create_lead(payload):
    conn = _get_db()
    lead_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO leads (id, name, email, phone, source, stage, notes, event_date, guest_count, message, checkin_status, brochure_sent, auto_reply_sent, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lead_id,
        payload.get("name", "Unknown"),
        payload.get("email", ""),
        payload.get("phone", ""),
        payload.get("source", "Other"),
        "New",
        payload.get("notes", ""),
        payload.get("event_date", ""),
        payload.get("guest_count", ""),
        payload.get("message", ""),
        "ID Requested",
        0,
        0,
        now,
        now
    ))
    conn.commit()
    
    if payload.get("message"):
        msg_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO messages (id, lead_id, direction, channel, body, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (msg_id, lead_id, "inbound", payload.get("source", "Other"), payload.get("message", ""), now))
        conn.commit()
    
    conn.close()
    
    _add_notification(f"New lead from {payload.get('name', 'Unknown')} via {payload.get('source', 'Other')}", lead_id)
    return get_lead(lead_id)


def update_lead(lead_id, payload):
    conn = _get_db()
    cursor = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    if not cursor.fetchone():
        conn.close()
        return None
    
    now = datetime.utcnow().isoformat()
    fields = []
    values = []
    allowed = ["name", "email", "phone", "source", "stage", "notes", "event_date", "guest_count", "win_loss", "checkin_status", "brochure_sent", "auto_reply_sent"]
    
    for key in allowed:
        if key in payload:
            fields.append(f"{key} = ?")
            val = payload[key]
            if key == "win_loss" and val:
                val = str(val)
            values.append(val)
    
    fields.append("updated_at = ?")
    values.append(now)
    values.append(lead_id)
    
    conn.execute(f"UPDATE leads SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return get_lead(lead_id)


def delete_lead(lead_id):
    conn = _get_db()
    cursor = conn.execute("SELECT id FROM leads WHERE id = ?", (lead_id,))
    if not cursor.fetchone():
        conn.close()
        return False
    conn.execute("DELETE FROM messages WHERE lead_id = ?", (lead_id,))
    conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()
    return True


def add_message_to_lead(lead_id, direction, channel, body):
    conn = _get_db()
    cursor = conn.execute("SELECT id FROM leads WHERE id = ?", (lead_id,))
    if not cursor.fetchone():
        conn.close()
        return None
    
    msg_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO messages (id, lead_id, direction, channel, body, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (msg_id, lead_id, direction, channel, body, now))
    
    conn.execute("UPDATE leads SET updated_at = ? WHERE id = ?", (now, lead_id))
    conn.commit()
    conn.close()
    
    return {"id": msg_id, "lead_id": lead_id, "direction": direction, "channel": channel, "body": body, "timestamp": now}


def get_stats():
    leads = get_all_leads()
    stage_counts = {s: 0 for s in LEAD_STAGES}
    source_counts = {s: 0 for s in SOURCES}
    
    for lead in leads:
        stage = lead.get("stage", "New")
        if stage in stage_counts:
            stage_counts[stage] += 1
        src = lead.get("source", "Other")
        if src in source_counts:
            source_counts[src] += 1
    
    won = [l for l in leads if l.get("stage") == "Won"]
    lost = [l for l in leads if l.get("stage") == "Lost"]
    
    return {
        "total": len(leads),
        "by_stage": stage_counts,
        "by_source": source_counts,
        "won": len(won),
        "lost": len(lost),
        "conversion_rate": round(len(won) / len(leads) * 100, 1) if leads else 0,
    }


def _add_notification(message, lead_id=None):
    conn = _get_db()
    notif_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO notifications (id, message, lead_id, read, timestamp)
        VALUES (?, ?, ?, 0, ?)
    """, (notif_id, message, lead_id, now))
    conn.commit()
    
    cursor = conn.execute("SELECT id FROM notifications ORDER BY timestamp DESC")
    all_notifs = cursor.fetchall()
    if len(all_notifs) > 50:
        keep_ids = [row[0] for row in all_notifs[:50]]
        conn.execute("DELETE FROM notifications WHERE id NOT IN ({})".format(",".join("?" * len(keep_ids))), keep_ids)
        conn.commit()
    
    conn.close()


def get_notifications():
    conn = _get_db()
    cursor = conn.execute("SELECT * FROM notifications ORDER BY timestamp DESC LIMIT 50")
    notifs = [_row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return notifs


def mark_notifications_read():
    conn = _get_db()
    conn.execute("UPDATE notifications SET read = 1")
    conn.commit()
    conn.close()