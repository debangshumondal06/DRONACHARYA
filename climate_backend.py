"""DRONACHARYA climate + market backend.

Register this blueprint in an existing Flask app; it does not replace app.py.
All external credentials belong in server-side environment variables.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, current_app, jsonify, request

climate_bp = Blueprint("climate", __name__, url_prefix="/api/climate")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "dronacharya_climate.sqlite3"
DEFAULT_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
OFFICIAL_NEWS = [
    {
        "title": "IMD Agromet Advisory Services",
        "summary": "State bulletins and crop advisories from the India Meteorological Department.",
        "url": "https://mausam.imd.gov.in/responsive/agromet_adv_ser_state_current.php",
    },
    {
        "title": "IMD Agricultural Meteorology Division",
        "summary": "Weather and climate services for agriculture, including farmer advisories.",
        "url": "https://imdagrimet.gov.in/",
    },
    {
        "title": "Agmarknet 2.0",
        "summary": "Official agricultural market information and mandi data portal.",
        "url": "https://agmarknet.gov.in/",
    },
]


def db_path() -> str:
    return current_app.config.get("CLIMATE_DB_PATH", os.getenv("DRONACHARYA_CLIMATE_DB", str(DEFAULT_DB)))


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_climate_db(path: str | None = None) -> None:
    target = path or current_app.config.get("CLIMATE_DB_PATH", os.getenv("DRONACHARYA_CLIMATE_DB", str(DEFAULT_DB)))
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_response(payload: dict[str, Any], status: int = 200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def http_json(url: str, params: dict[str, Any] | None = None, timeout: int = 12) -> dict[str, Any]:
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urlencode({k: v for k, v in params.items() if v is not None})}"
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "DRONACHARYA/1.0"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def record_refresh(feed: str, source: str, status: str, records: int = 0, error: str | None = None) -> None:
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO feed_refresh_logs(feed_name, source_name, status, completed_at, records_written, error_message) VALUES (?, ?, ?, ?, ?, ?)",
                (feed, source, status, now_iso(), records, error),
            )
    except sqlite3.Error:
        current_app.logger.exception("Climate refresh log failed")


def coordinate_args() -> tuple[float, float] | None:
    try:
        lat = float(request.args.get("lat", ""))
        lon = float(request.args.get("lon", ""))
    except ValueError:
        return None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


@climate_bp.get("/health")
def climate_health():
    configured = {
        "weather": True,
        "market": bool(os.getenv("DRONACHARYA_MARKET_API_URL")),
        "news": bool(os.getenv("DRONACHARYA_NEWS_API_URL")),
    }
    return json_response({"ok": True, "service": "dronacharya-climate", "configured": configured, "time": now_iso()})


@climate_bp.get("/weather")
def weather():
    coords = coordinate_args()
    if coords is None:
        return json_response({"ok": False, "error": "Valid lat and lon query parameters are required."}, 400)
    lat, lon = coords
    try:
        payload = http_json(
            os.getenv("DRONACHARYA_WEATHER_API_URL", DEFAULT_WEATHER_URL),
            {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
                "forecast_days": 14,
                "timezone": "auto",
            },
        )
        current = payload.get("current", {})
        daily = payload.get("daily", {})
        days = []
        for i, day in enumerate(daily.get("time", [])):
            days.append({
                "date": day,
                "temperature_max": (daily.get("temperature_2m_max") or [None])[i],
                "temperature_min": (daily.get("temperature_2m_min") or [None])[i],
                "precipitation_sum": (daily.get("precipitation_sum") or [None])[i],
                "precipitation_probability": (daily.get("precipitation_probability_max") or [None])[i],
                "wind_max": (daily.get("wind_speed_10m_max") or [None])[i],
            })
        with get_db() as conn:
            location_id = conn.execute(
                "SELECT id FROM farm_locations WHERE abs(latitude-?) < 0.00001 AND abs(longitude-?) < 0.00001 LIMIT 1", (lat, lon)
            ).fetchone()
            if location_id is None:
                cur = conn.execute("INSERT INTO farm_locations(label, latitude, longitude, timezone) VALUES (?, ?, ?, ?)", (f"{lat:.4f}, {lon:.4f}", lat, lon, payload.get("timezone")))
                location_id = {"id": cur.lastrowid}
            conn.execute(
                "INSERT INTO weather_observations(location_id, source, observed_at, temperature_c, wind_speed_kmh, raw_payload) VALUES (?, ?, ?, ?, ?, ?)",
                (location_id["id"], "open_meteo", now_iso(), current.get("temperature_2m"), current.get("wind_speed_10m"), json.dumps(payload)),
            )
            for day in days:
                conn.execute(
                    "INSERT OR REPLACE INTO weather_forecast_days(location_id, source, forecast_date, temperature_max_c, temperature_min_c, precipitation_sum_mm, precipitation_probability_percent, wind_max_kmh, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (location_id["id"], "open_meteo", day["date"], day["temperature_max"], day["temperature_min"], day["precipitation_sum"], day["precipitation_probability"], day["wind_max"], now_iso()),
                )
        record_refresh("weather", "open_meteo", "healthy", len(days))
        return json_response({"ok": True, "source": "open_meteo", "timezone": payload.get("timezone"), "current": current, "days": days, "fetched_at": now_iso()})
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        record_refresh("weather", "open_meteo", "failed", error=str(exc))
        return json_response({"ok": False, "source": "open_meteo", "error": "Weather provider unavailable."}, 502)


@climate_bp.get("/market-prices")
def market_prices():
    crop = request.args.get("crop", "").strip().lower()
    state = request.args.get("state", "").strip().upper()
    endpoint = os.getenv("DRONACHARYA_MARKET_API_URL")
    if not endpoint:
        return json_response({"ok": False, "connected": False, "error": "No server-side market provider is configured.", "sources": ["https://agmarknet.gov.in/", "https://data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi"]}, 503)
    try:
        payload = http_json(endpoint, {"crop": crop, "state": state, "market": request.args.get("market")})
        normalized = normalize_market(payload)
        record_refresh("market", endpoint, "healthy", 1 if normalized.get("latest_price") is not None else 0)
        return json_response({"ok": True, "connected": True, **normalized})
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        record_refresh("market", endpoint, "failed", error=str(exc))
        return json_response({"ok": False, "connected": True, "error": "Configured market provider unavailable."}, 502)


def normalize_market(payload: dict[str, Any]) -> dict[str, Any]:
    series = payload.get("series") or payload.get("prices") or []
    if isinstance(series, dict):
        series = list(series.values())
    return {
        "latest_price": payload.get("latest_price", payload.get("modal_price")),
        "change_percent": payload.get("change_percent", payload.get("change")),
        "market": payload.get("market", payload.get("mandi_name")),
        "observed_at": payload.get("observed_at", payload.get("updated_at")),
        "series": [float(v) for v in series if isinstance(v, (int, float))],
        "currency": payload.get("currency", "INR"),
        "unit": payload.get("unit", "quintal"),
    }


@climate_bp.get("/news")
def news():
    endpoint = os.getenv("DRONACHARYA_NEWS_API_URL")
    if not endpoint:
        return json_response({"ok": True, "connected": False, "items": OFFICIAL_NEWS, "source_state": "official-links"})
    try:
        payload = http_json(endpoint, {"crop": request.args.get("crop"), "state": request.args.get("state")})
        items = payload.get("items", []) if isinstance(payload, dict) else []
        clean = [{"title": str(x.get("title", "Untitled headline")), "summary": str(x.get("summary", "")), "url": str(x.get("url", "#")), "published_at": x.get("published_at")} for x in items if isinstance(x, dict)]
        with get_db() as conn:
            for item in clean:
                content_hash = hashlib.sha256(f"{item['title']}|{item['url']}".encode()).hexdigest()
                conn.execute("INSERT OR IGNORE INTO agriculture_news_items(source_name, source_url, title, summary, published_at, content_hash) VALUES (?, ?, ?, ?, ?, ?)", ("configured-provider", item["url"], item["title"], item["summary"], item["published_at"], content_hash))
        record_refresh("news", endpoint, "healthy", len(clean))
        return json_response({"ok": True, "connected": True, "items": clean, "source_state": "live"})
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        record_refresh("news", endpoint, "failed", error=str(exc))
        return json_response({"ok": False, "connected": True, "items": OFFICIAL_NEWS, "source_state": "official-links", "error": "Configured news provider unavailable."}, 502)


@climate_bp.route("/watchlist", methods=["GET", "POST"])
def watchlist():
    user_id = request.args.get("user_id") or (request.get_json(silent=True) or {}).get("user_id") or "anonymous"
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        crop = str(body.get("crop", "")).strip().lower()
        state = str(body.get("state", "")).strip().upper()
        if not crop or not state:
            return json_response({"ok": False, "error": "crop and state are required."}, 400)
        with get_db() as conn:
            conn.execute("INSERT OR IGNORE INTO watchlists(user_id, crop_code, state_code) VALUES (?, ?, ?)", (user_id, crop, state))
    with get_db() as conn:
        rows = conn.execute("SELECT crop_code, state_code, created_at FROM watchlists WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
    return json_response({"ok": True, "user_id": user_id, "items": [dict(row) for row in rows]})


SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS farm_locations (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, label TEXT NOT NULL, village TEXT, district TEXT, state_code TEXT, latitude REAL NOT NULL CHECK(latitude BETWEEN -90 AND 90), longitude REAL NOT NULL CHECK(longitude BETWEEN -180 AND 180), timezone TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS weather_observations (id INTEGER PRIMARY KEY AUTOINCREMENT, location_id INTEGER NOT NULL REFERENCES farm_locations(id) ON DELETE CASCADE, source TEXT NOT NULL, observed_at TEXT NOT NULL, temperature_c REAL, apparent_temperature_c REAL, precipitation_mm REAL, humidity_percent REAL, wind_speed_kmh REAL, weather_code INTEGER, raw_payload TEXT NOT NULL DEFAULT '{}', fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(location_id, source, observed_at));
CREATE TABLE IF NOT EXISTS weather_forecast_days (id INTEGER PRIMARY KEY AUTOINCREMENT, location_id INTEGER NOT NULL REFERENCES farm_locations(id) ON DELETE CASCADE, source TEXT NOT NULL, forecast_date TEXT NOT NULL, temperature_max_c REAL, temperature_min_c REAL, precipitation_sum_mm REAL, precipitation_probability_percent REAL, wind_max_kmh REAL, weather_code INTEGER, fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(location_id, source, forecast_date, fetched_at));
CREATE TABLE IF NOT EXISTS agriculture_news_items (id INTEGER PRIMARY KEY AUTOINCREMENT, crop_code TEXT, source_name TEXT NOT NULL, source_url TEXT NOT NULL, title TEXT NOT NULL, summary TEXT, published_at TEXT, fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, content_hash TEXT NOT NULL UNIQUE, is_active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS watchlists (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, crop_code TEXT NOT NULL, state_code TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, crop_code, state_code));
CREATE TABLE IF NOT EXISTS feed_refresh_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, feed_name TEXT NOT NULL CHECK(feed_name IN ('weather','market','news')), source_name TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('healthy','degraded','failed')), requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT, records_written INTEGER NOT NULL DEFAULT 0, error_message TEXT, metadata TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS idx_weather_location_time ON weather_observations(location_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_forecast_location_date ON weather_forecast_days(location_id, forecast_date);
CREATE INDEX IF NOT EXISTS idx_news_crop_time ON agriculture_news_items(crop_code, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlists(user_id, created_at DESC);
"""


def register_climate(app):
    """Register routes and initialize SQLite without replacing existing app.py routes."""
    app.config.setdefault("CLIMATE_DB_PATH", os.getenv("DRONACHARYA_CLIMATE_DB", str(DEFAULT_DB)))
    app.register_blueprint(climate_bp)
    # Compatibility path used by the standalone climate-market HTML page.
    # The endpoint name is unique so it cannot collide with an existing app route.
    if "climate_market_prices_compat" not in app.view_functions:
        app.add_url_rule("/api/market-prices", endpoint="climate_market_prices_compat", view_func=market_prices, methods=["GET"])
    with app.app_context():
        init_climate_db()
    return app
