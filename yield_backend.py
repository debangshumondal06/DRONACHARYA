"""
DRONACHARYA — Estimate Yield backend
-------------------------------------
Plain Flask + SQLite (no ORM), designed as a drop-in Blueprint.

Integration into your existing app.py:

    from yield_backend import yield_bp, init_db

    app = Flask(__name__)
    app.secret_key = "replace-with-a-real-secret-key"   # required for session-based history
    app.register_blueprint(yield_bp)

    with app.app_context():
        init_db()

Then make sure `templates/estimate_yield.html` (the file delivered alongside this
one) sits in your `templates/` folder, and that your existing routes named
`home`, `field_visit`, `store`, and `login` exist (the template's url_for()
calls depend on those names, not yours specifically — rename either side to
match).

Routes exposed by this blueprint:
    GET  /estimate-yield            -> renders the dashboard page
    POST /api/estimate              -> computes a report, saves it, returns JSON
    GET  /api/history               -> list of this visitor's saved reports (summary)
    GET  /api/history/<id>          -> full stored report (JSON)
    GET  /api/history/<id>/csv      -> same report as a downloadable CSV

History is scoped per-visitor using a random id stored in the Flask session
cookie — no login is required to use Estimate Yield, but a signed-in user's
reports won't yet follow them across devices. If/when your auth system is
wired up, swap `get_session_id()` to key off the logged-in user's id instead.
"""

import csv
import io
import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from flask import Blueprint, Response, jsonify, request, session

yield_bp = Blueprint("yield_bp", __name__)

DB_PATH = Path(__file__).resolve().parent / "database" / "dronacharya.db"

# ---------------------------------------------------------------------------
# Reference agronomy data (static — mirrors the JS copy used for map labels).
# These are illustrative reference coefficients, not an official ICAR feed.
# Swap in real figures from your state agriculture department when available.
# ---------------------------------------------------------------------------

BASE_YIELD_QTL_PER_ACRE = {
    "rice": 22, "wheat": 18, "maize": 20, "cotton": 6, "sugarcane": 300, "pulses": 8,
}

SOIL_FACTOR = {
    "rice":      {"alluvial": 1.08, "black": 0.95, "red": 0.85, "laterite": 0.90, "arid": 0.55, "mountain": 0.80, "saline": 0.60},
    "wheat":     {"alluvial": 1.12, "black": 1.00, "red": 0.82, "laterite": 0.78, "arid": 0.60, "mountain": 0.85, "saline": 0.62},
    "maize":     {"alluvial": 1.05, "black": 1.02, "red": 0.90, "laterite": 0.85, "arid": 0.65, "mountain": 0.88, "saline": 0.65},
    "cotton":    {"alluvial": 0.95, "black": 1.15, "red": 0.90, "laterite": 0.70, "arid": 0.70, "mountain": 0.60, "saline": 0.65},
    "sugarcane": {"alluvial": 1.15, "black": 1.05, "red": 0.85, "laterite": 0.80, "arid": 0.50, "mountain": 0.60, "saline": 0.55},
    "pulses":    {"alluvial": 1.00, "black": 1.05, "red": 0.95, "laterite": 0.85, "arid": 0.75, "mountain": 0.80, "saline": 0.70},
}

IRRIGATION_FACTOR = {
    "drip": 1.18, "sprinkler": 1.10, "canal": 1.00, "tubewell": 0.98, "rainfed": 0.72,
}

IDEAL_PH = {
    "rice": 6.0, "wheat": 6.8, "maize": 6.3, "cotton": 7.2, "sugarcane": 6.8, "pulses": 6.5,
}

IDEAL_MONTHLY_RAIN_MM = {
    "rice": 200, "wheat": 60, "maize": 90, "cotton": 70, "sugarcane": 150, "pulses": 55,
}

CROP_LABELS = {"rice": "Rice", "wheat": "Wheat", "maize": "Maize", "cotton": "Cotton", "sugarcane": "Sugarcane", "pulses": "Pulses"}
SOIL_LABELS = {"alluvial": "Alluvial", "black": "Black (Regur)", "red": "Red & Yellow", "laterite": "Laterite", "arid": "Arid / Desert", "mountain": "Mountain / Forest", "saline": "Saline / Alkaline"}
IRRIGATION_LABELS = {"drip": "Drip", "sprinkler": "Sprinkler", "canal": "Canal / flood", "tubewell": "Groundwater / tubewell", "rainfed": "Rainfed (none)"}

VALID_CROPS = set(BASE_YIELD_QTL_PER_ACRE)
VALID_SOILS = {"alluvial", "black", "red", "laterite", "arid", "mountain", "saline"}
VALID_IRRIGATION = set(IRRIGATION_FACTOR)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the yield_reports table if it doesn't exist yet. Safe to call on every startup."""
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS yield_reports (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            place           TEXT NOT NULL,
            latitude        REAL,
            longitude       REAL,
            crop            TEXT NOT NULL,
            soil_type       TEXT NOT NULL,
            irrigation_type TEXT NOT NULL,
            ph              REAL NOT NULL,
            area_input      REAL NOT NULL,
            area_unit       TEXT NOT NULL,
            area_acres      REAL NOT NULL,
            per_acre_yield  REAL NOT NULL,
            total_yield     REAL NOT NULL,
            confidence_low  REAL NOT NULL,
            confidence_high REAL NOT NULL,
            rainfall_30d_mm REAL,
            weather_source  TEXT NOT NULL,
            result_json     TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_yield_reports_session ON yield_reports(session_id)")
    conn.commit()
    conn.close()


def get_session_id():
    if session.get("user_id") is not None:
        return f"user:{session['user_id']}"

    if "yield_session_id" not in session:
        session["yield_session_id"] = uuid.uuid4().hex

    return f"visitor:{session['yield_session_id']}"

# ---------------------------------------------------------------------------
# External data: geocoding + rainfall (Open-Meteo — free, keyless, CORS-friendly)
# ---------------------------------------------------------------------------

def geocode_place(place_name):
    """Resolve a free-text place name to coordinates. Returns (lat, lng, resolved_name) or (None, None, None)."""
    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": place_name, "count": 1, "country": "IN"},
            timeout=6,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        if results:
            r = results[0]
            return r["latitude"], r["longitude"], r.get("name", place_name)
    except (requests.RequestException, ValueError, KeyError):
        pass
    return None, None, None


def fetch_rainfall(lat, lng):
    """Last 30 days of daily precipitation for a coordinate. Returns (dates, values) or (None, None)."""
    try:
        end = date.today()
        start = end - timedelta(days=29)
        resp = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": lat,
                "longitude": lng,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": "precipitation_sum",
                "timezone": "auto",
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily") or {}
        values = daily.get("precipitation_sum")
        dates = daily.get("time")
        if values and dates:
            return dates, [v if v is not None else 0.0 for v in values]
    except (requests.RequestException, ValueError, KeyError):
        pass
    return None, None


def clamp(value, low, high):
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# Calculation engine
# ---------------------------------------------------------------------------

def compute_report(payload):
    """Validate inputs, pull live weather, and compute the yield report dict.
    Raises ValueError on bad input (caller should turn that into a 400)."""

    place = (payload.get("place") or "").strip() or "Selected location"
    crop = payload.get("crop", "wheat")
    soil = payload.get("soilType", "alluvial")
    irrigation = payload.get("irrigation", "canal")

    if crop not in VALID_CROPS:
        raise ValueError(f"Unknown crop '{crop}'")
    if soil not in VALID_SOILS:
        raise ValueError(f"Unknown soil type '{soil}'")
    if irrigation not in VALID_IRRIGATION:
        raise ValueError(f"Unknown irrigation type '{irrigation}'")

    try:
        ph = float(payload.get("ph", 6.5))
        area = float(payload.get("area", 1))
    except (TypeError, ValueError):
        raise ValueError("area and ph must be numbers")

    ph = clamp(ph, 3.0, 10.0)
    area = max(0.1, area)
    area_unit = payload.get("areaUnit", "acre")
    area_acres = area * 2.471 if area_unit == "hectare" else area

    lat = payload.get("lat")
    lng = payload.get("lng")
    if lat is None or lng is None:
        lat, lng, _resolved = geocode_place(place)

    rainfall_dates, rainfall_values = (None, None)
    rainfall_total = None
    rainfall_source = "No location match"
    if lat is not None and lng is not None:
        rainfall_dates, rainfall_values = fetch_rainfall(lat, lng)
        if rainfall_values:
            rainfall_total = sum(rainfall_values)
            rainfall_source = "Open-Meteo, live"

    ideal_monthly = IDEAL_MONTHLY_RAIN_MM[crop]
    weather_factor = clamp(rainfall_total / ideal_monthly, 0.65, 1.2) if rainfall_total is not None else 0.85

    soil_factor = SOIL_FACTOR[crop][soil]
    irrigation_factor = IRRIGATION_FACTOR[irrigation]

    ideal_ph = IDEAL_PH[crop]
    ph_diff = abs(ph - ideal_ph)
    ph_factor = clamp(1 - min(ph_diff / 4, 1) * 0.45, 0.5, 1.05)

    per_acre = BASE_YIELD_QTL_PER_ACRE[crop] * soil_factor * irrigation_factor * ph_factor * weather_factor
    variance = 0.10 if rainfall_total is not None else 0.18
    total_yield = per_acre * area_acres

    report = {
        "place": place,
        "crop": crop,
        "soil": soil,
        "irrigation": irrigation,
        "ph": ph,
        "areaAcres": area_acres,
        "perAcre": per_acre,
        "totalYield": total_yield,
        "low": per_acre * (1 - variance),
        "high": per_acre * (1 + variance),
        "rainfallTotal": rainfall_total,
        "rainfallDates": [d[5:] for d in rainfall_dates] if rainfall_dates else [],
        "rainfallValues": rainfall_values or [],
        "rainfallSource": rainfall_source,
        "factors": {
            "soil": soil_factor,
            "irrigation": irrigation_factor,
            "ph": ph_factor,
            "weather": weather_factor,
        },
        "createdAt": datetime.utcnow().isoformat() + "Z",
        "lat": lat,
        "lng": lng,
        "areaInput": area,
        "areaUnit": area_unit,
    }
    return report


def save_report(session_id, report):
    conn = get_db()
    cur = conn.execute(
        """
        INSERT INTO yield_reports (
            session_id, created_at, place, latitude, longitude, crop, soil_type,
            irrigation_type, ph, area_input, area_unit, area_acres, per_acre_yield,
            total_yield, confidence_low, confidence_high, rainfall_30d_mm,
            weather_source, result_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id, report["createdAt"], report["place"], report["lat"], report["lng"],
            report["crop"], report["soil"], report["irrigation"], report["ph"],
            report["areaInput"], report["areaUnit"], report["areaAcres"], report["perAcre"],
            report["totalYield"], report["low"], report["high"], report["rainfallTotal"],
            report["rainfallSource"], json.dumps(report),
        ),
    )
    conn.commit()
    report_id = cur.lastrowid
    conn.close()
    return report_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@yield_bp.route("/api/estimate", methods=["POST"])
def api_estimate():
    payload = request.get_json(silent=True) or {}
    try:
        report = compute_report(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    session_id = get_session_id()
    report["id"] = save_report(session_id, report)
    return jsonify(report)


@yield_bp.route("/api/history")
def api_history():
    session_id = get_session_id()
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, place, crop, total_yield, created_at
        FROM yield_reports
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT 30
        """,
        (session_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@yield_bp.route("/api/history/<int:report_id>")
def api_history_detail(report_id):
    session_id = get_session_id()
    conn = get_db()
    row = conn.execute(
        "SELECT result_json FROM yield_reports WHERE id = ? AND session_id = ?",
        (report_id, session_id),
    ).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "Report not found"}), 404
    report = json.loads(row["result_json"])
    report["id"] = report_id
    return jsonify(report)


@yield_bp.route("/api/history/<int:report_id>/csv")
def api_history_csv(report_id):
    session_id = get_session_id()
    conn = get_db()
    row = conn.execute(
        "SELECT result_json FROM yield_reports WHERE id = ? AND session_id = ?",
        (report_id, session_id),
    ).fetchone()
    conn.close()
    if row is None:
        return Response("Report not found", status=404, mimetype="text/plain")

    report = json.loads(row["result_json"])
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Field", "Value"])
    writer.writerow(["Place", report["place"]])
    writer.writerow(["Crop", CROP_LABELS.get(report["crop"], report["crop"])])
    writer.writerow(["Soil type", SOIL_LABELS.get(report["soil"], report["soil"])])
    writer.writerow(["Irrigation", IRRIGATION_LABELS.get(report["irrigation"], report["irrigation"])])
    writer.writerow(["Area (acres)", f"{report['areaAcres']:.2f}"])
    writer.writerow(["Soil pH", f"{report['ph']:.1f}"])
    writer.writerow(["Rainfall 30d (mm)", f"{report['rainfallTotal']:.1f}" if report["rainfallTotal"] is not None else "N/A"])
    writer.writerow(["Estimated yield / acre (qtl)", f"{report['perAcre']:.2f}"])
    writer.writerow(["Total estimated yield (qtl)", f"{report['totalYield']:.2f}"])
    writer.writerow(["Confidence low (qtl/acre)", f"{report['low']:.2f}"])
    writer.writerow(["Confidence high (qtl/acre)", f"{report['high']:.2f}"])
    writer.writerow(["Soil factor", f"{report['factors']['soil']:.3f}"])
    writer.writerow(["Irrigation factor", f"{report['factors']['irrigation']:.3f}"])
    writer.writerow(["pH factor", f"{report['factors']['ph']:.3f}"])
    writer.writerow(["Weather factor", f"{report['factors']['weather']:.3f}"])
    writer.writerow(["Generated at (UTC)", report["createdAt"]])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=dronacharya-yield-{report_id}.csv"},
    )