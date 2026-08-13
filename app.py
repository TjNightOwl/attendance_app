"""
Meeting Attendance Scanner
--------------------------
A mobile-friendly web app for scanning participant name-tag QR codes to
confirm attendance across one or more meeting days.

Run with:  python app.py
Then open the printed URL on the phone that will do the scanning.
See README.md for notes on camera permissions (HTTPS/localhost requirement).
"""

import csv
import io
import os
import sqlite3
import uuid
from datetime import datetime, timedelta

import qrcode
from flask import (
    Flask, g, render_template, request, redirect, url_for,
    send_file, jsonify, flash, abort
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "attendance.db")
QR_DIR = os.path.join(BASE_DIR, "static", "qrcodes")
os.makedirs(QR_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = "change-this-secret-key"  # only used for flash messages


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,   -- YYYY-MM-DD
            end_date TEXT NOT NULL,     -- YYYY-MM-DD
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            organization TEXT,
            code TEXT NOT NULL UNIQUE,   -- what's encoded in the QR
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
            meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
            date TEXT NOT NULL,          -- YYYY-MM-DD, the specific day attended
            scanned_at TEXT NOT NULL,
            UNIQUE(participant_id, date)
        );
        """
    )
    db.commit()
    db.close()


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def daterange(start_date: str, end_date: str):
    """Return list of YYYY-MM-DD strings from start to end inclusive."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    days = []
    d = start
    while d <= end:
        days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def get_meeting_or_404(meeting_id):
    db = get_db()
    meeting = db.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    if meeting is None:
        abort(404)
    return meeting


def qr_path_for(code: str) -> str:
    return os.path.join(QR_DIR, f"{code}.png")


def ensure_qr_image(code: str):
    path = qr_path_for(code)
    if not os.path.exists(path):
        img = qrcode.make(code)
        img.save(path)
    return path


# --------------------------------------------------------------------------
# Routes: meetings
# --------------------------------------------------------------------------
@app.route("/")
def index():
    db = get_db()
    meetings = db.execute(
        "SELECT * FROM meetings ORDER BY start_date DESC"
    ).fetchall()
    return render_template("index.html", meetings=meetings)


@app.route("/meetings/new", methods=["GET", "POST"])
def new_meeting():
    if request.method == "POST":
        name = request.form["name"].strip()
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]

        if not name or not start_date or not end_date:
            flash("Please fill in all fields.", "error")
            return render_template("new_meeting.html")

        if end_date < start_date:
            flash("End date cannot be before start date.", "error")
            return render_template("new_meeting.html")

        db = get_db()
        cur = db.execute(
            "INSERT INTO meetings (name, start_date, end_date, created_at) VALUES (?, ?, ?, ?)",
            (name, start_date, end_date, datetime.now().isoformat()),
        )
        db.commit()
        flash("Meeting created.", "success")
        return redirect(url_for("meeting_detail", meeting_id=cur.lastrowid))

    return render_template("new_meeting.html")


@app.route("/meetings/<int:meeting_id>")
def meeting_detail(meeting_id):
    meeting = get_meeting_or_404(meeting_id)
    db = get_db()
    participants = db.execute(
        "SELECT * FROM participants WHERE meeting_id = ? ORDER BY name",
        (meeting_id,),
    ).fetchall()
    days = daterange(meeting["start_date"], meeting["end_date"])
    return render_template(
        "meeting_detail.html", meeting=meeting, participants=participants, days=days
    )


@app.route("/meetings/<int:meeting_id>/delete", methods=["POST"])
def delete_meeting(meeting_id):
    get_meeting_or_404(meeting_id)
    db = get_db()
    db.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
    db.commit()
    flash("Meeting deleted.", "success")
    return redirect(url_for("index"))


# --------------------------------------------------------------------------
# Routes: participants / QR generation
# --------------------------------------------------------------------------
@app.route("/meetings/<int:meeting_id>/participants/new", methods=["POST"])
def new_participant(meeting_id):
    get_meeting_or_404(meeting_id)
    name = request.form["name"].strip()
    organization = request.form.get("organization", "").strip()

    if not name:
        flash("Participant name is required.", "error")
        return redirect(url_for("meeting_detail", meeting_id=meeting_id))

    code = f"P-{uuid.uuid4().hex[:10].upper()}"
    db = get_db()
    db.execute(
        "INSERT INTO participants (meeting_id, name, organization, code, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (meeting_id, name, organization, code, datetime.now().isoformat()),
    )
    db.commit()
    ensure_qr_image(code)
    flash(f"Added {name} and generated their QR tag.", "success")
    return redirect(url_for("meeting_detail", meeting_id=meeting_id))


@app.route("/meetings/<int:meeting_id>/participants/<int:pid>/delete", methods=["POST"])
def delete_participant(meeting_id, pid):
    db = get_db()
    db.execute(
        "DELETE FROM participants WHERE id = ? AND meeting_id = ?", (pid, meeting_id)
    )
    db.commit()
    flash("Participant removed.", "success")
    return redirect(url_for("meeting_detail", meeting_id=meeting_id))


@app.route("/meetings/<int:meeting_id>/badge/<int:pid>")
def badge(meeting_id, pid):
    meeting = get_meeting_or_404(meeting_id)
    db = get_db()
    participant = db.execute(
        "SELECT * FROM participants WHERE id = ? AND meeting_id = ?", (pid, meeting_id)
    ).fetchone()
    if participant is None:
        abort(404)
    ensure_qr_image(participant["code"])
    return render_template("badge.html", meeting=meeting, participants=[participant])


@app.route("/meetings/<int:meeting_id>/badges")
def badges_all(meeting_id):
    meeting = get_meeting_or_404(meeting_id)
    db = get_db()
    participants = db.execute(
        "SELECT * FROM participants WHERE meeting_id = ? ORDER BY name", (meeting_id,)
    ).fetchall()
    for p in participants:
        ensure_qr_image(p["code"])
    return render_template("badge.html", meeting=meeting, participants=participants)


# --------------------------------------------------------------------------
# Routes: scanning
# --------------------------------------------------------------------------
@app.route("/meetings/<int:meeting_id>/scan")
def scan_page(meeting_id):
    meeting = get_meeting_or_404(meeting_id)
    days = daterange(meeting["start_date"], meeting["end_date"])
    today = datetime.now().date().isoformat()
    default_day = today if today in days else days[0]
    return render_template(
        "scan.html", meeting=meeting, days=days, default_day=default_day
    )


@app.route("/meetings/<int:meeting_id>/scan", methods=["POST"])
def scan_submit(meeting_id):
    """Called via fetch() from the scan page's JS every time a QR code is read."""
    meeting = get_meeting_or_404(meeting_id)
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("code") or "").strip()
    date = (data.get("date") or "").strip()

    valid_days = daterange(meeting["start_date"], meeting["end_date"])
    if date not in valid_days:
        return jsonify(status="error", message="Selected date is outside the meeting range."), 400

    db = get_db()
    participant = db.execute(
        "SELECT * FROM participants WHERE code = ? AND meeting_id = ?", (code, meeting_id)
    ).fetchone()

    if participant is None:
        return jsonify(status="error", message="QR code not recognized for this meeting."), 404

    existing = db.execute(
        "SELECT 1 FROM attendance WHERE participant_id = ? AND date = ?",
        (participant["id"], date),
    ).fetchone()

    if existing:
        return jsonify(
            status="duplicate",
            message=f"{participant['name']} already checked in for {date}.",
            name=participant["name"],
        )

    db.execute(
        "INSERT INTO attendance (participant_id, meeting_id, date, scanned_at) VALUES (?, ?, ?, ?)",
        (participant["id"], meeting_id, date, datetime.now().isoformat()),
    )
    db.commit()
    return jsonify(
        status="ok",
        message=f"Checked in: {participant['name']}",
        name=participant["name"],
        organization=participant["organization"] or "",
    )


# --------------------------------------------------------------------------
# Routes: reports
# --------------------------------------------------------------------------
@app.route("/meetings/<int:meeting_id>/report")
def report(meeting_id):
    meeting = get_meeting_or_404(meeting_id)
    db = get_db()
    days = daterange(meeting["start_date"], meeting["end_date"])
    participants = db.execute(
        "SELECT * FROM participants WHERE meeting_id = ? ORDER BY name", (meeting_id,)
    ).fetchall()
    attendance_rows = db.execute(
        "SELECT participant_id, date FROM attendance WHERE meeting_id = ?", (meeting_id,)
    ).fetchall()

    attended = {}  # participant_id -> set of dates
    for row in attendance_rows:
        attended.setdefault(row["participant_id"], set()).add(row["date"])

    table = []
    for p in participants:
        p_attended = attended.get(p["id"], set())
        table.append(
            {
                "participant": p,
                "flags": [d in p_attended for d in days],
                "total": len(p_attended),
            }
        )

    return render_template(
        "report.html", meeting=meeting, days=days, table=table
    )


@app.route("/meetings/<int:meeting_id>/report.csv")
def report_csv(meeting_id):
    meeting = get_meeting_or_404(meeting_id)
    db = get_db()
    days = daterange(meeting["start_date"], meeting["end_date"])
    participants = db.execute(
        "SELECT * FROM participants WHERE meeting_id = ? ORDER BY name", (meeting_id,)
    ).fetchall()
    attendance_rows = db.execute(
        "SELECT participant_id, date FROM attendance WHERE meeting_id = ?", (meeting_id,)
    ).fetchall()

    attended = {}
    for row in attendance_rows:
        attended.setdefault(row["participant_id"], set()).add(row["date"])

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Organization"] + days + ["Days Attended"])
    for p in participants:
        p_attended = attended.get(p["id"], set())
        row = [p["name"], p["organization"] or ""]
        row += ["Yes" if d in p_attended else "No" for d in days]
        row.append(len(p_attended))
        writer.writerow(row)

    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    filename = f"{meeting['name'].replace(' ', '_')}_attendance.csv"
    return send_file(
        mem, mimetype="text/csv", as_attachment=True, download_name=filename
    )


if __name__ == "__main__":
    init_db()
    # host=0.0.0.0 so phones on the same network can reach it via your computer's IP.
    # ssl_context="adhoc" gives a self-signed HTTPS cert -- most mobile browsers
    # require HTTPS (or localhost) to grant camera access for QR scanning.
    app.run(host="0.0.0.0", port=5000, debug=True, ssl_context="adhoc")
