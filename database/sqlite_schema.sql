CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aadhaar_hash TEXT NOT NULL,
    phone_hash TEXT NOT NULL,
    aadhaar_last4 TEXT NOT NULL,
    phone_last4 TEXT NOT NULL,
    email TEXT,
    created_at TEXT NOT NULL,
    last_login_at TEXT NOT NULL,
    UNIQUE (aadhaar_hash, phone_hash)
);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    target_column TEXT,
    report_json TEXT NOT NULL,
    prediction_json TEXT NOT NULL,
    recommendations_json TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id);

CREATE TABLE IF NOT EXISTS yield_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    place TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    crop TEXT NOT NULL,
    soil_type TEXT NOT NULL,
    irrigation_type TEXT NOT NULL,
    ph REAL NOT NULL,
    area_input REAL NOT NULL,
    area_unit TEXT NOT NULL,
    area_acres REAL NOT NULL,
    per_acre_yield REAL NOT NULL,
    total_yield REAL NOT NULL,
    confidence_low REAL NOT NULL,
    confidence_high REAL NOT NULL,
    rainfall_30d_mm REAL,
    weather_source TEXT NOT NULL,
    result_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_yield_reports_session ON yield_reports(session_id);

CREATE TABLE IF NOT EXISTS field_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_code TEXT NOT NULL UNIQUE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'submitted',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_field_visits_user_id
    ON field_visits(user_id);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    seller_name TEXT NOT NULL,
    seller_contact TEXT NOT NULL,
    crop_name TEXT NOT NULL,
    category TEXT NOT NULL,
    quantity REAL NOT NULL CHECK (quantity > 0),
    unit TEXT NOT NULL,
    price_per_unit REAL NOT NULL CHECK (price_per_unit >= 0),
    harvest_date TEXT,
    location TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    buyer_name TEXT NOT NULL,
    buyer_contact TEXT NOT NULL,
    buyer_address TEXT NOT NULL,
    total_amount REAL NOT NULL CHECK (total_amount >= 0),
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    seller_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK (quantity > 0),
    unit_price REAL NOT NULL CHECK (unit_price >= 0),
    line_total REAL NOT NULL CHECK (line_total >= 0)
);
-- DRONACHARYA climate + market SQLite migration
-- Run once with: sqlite3 your_database.db < climate-market-schema.sqlite.sql

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS farm_locations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  label TEXT NOT NULL,
  village TEXT,
  district TEXT,
  state_code TEXT,
  latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  timezone TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS weather_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  location_id INTEGER NOT NULL REFERENCES farm_locations(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  temperature_c REAL,
  apparent_temperature_c REAL,
  precipitation_mm REAL,
  humidity_percent REAL,
  wind_speed_kmh REAL,
  weather_code INTEGER,
  raw_payload TEXT NOT NULL DEFAULT '{}',
  fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(location_id, source, observed_at)
);

CREATE TABLE IF NOT EXISTS weather_forecast_days (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  location_id INTEGER NOT NULL REFERENCES farm_locations(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  forecast_date TEXT NOT NULL,
  temperature_max_c REAL,
  temperature_min_c REAL,
  precipitation_sum_mm REAL,
  precipitation_probability_percent REAL,
  wind_max_kmh REAL,
  weather_code INTEGER,
  fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(location_id, source, forecast_date, fetched_at)
);

CREATE TABLE IF NOT EXISTS market_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_code TEXT NOT NULL,
  display_name TEXT NOT NULL,
  endpoint_url TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER REFERENCES market_sources(id) ON DELETE SET NULL,
  crop_code TEXT,
  commodity_name TEXT NOT NULL,
  state_code TEXT,
  district TEXT,
  mandi_name TEXT,
  variety TEXT,
  grade TEXT,
  unit TEXT NOT NULL DEFAULT 'quintal',
  min_price REAL,
  modal_price REAL,
  max_price REAL,
  arrival_quantity REAL,
  currency TEXT NOT NULL DEFAULT 'INR',
  observed_at TEXT NOT NULL,
  raw_payload TEXT NOT NULL DEFAULT '{}',
  fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agriculture_news_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  crop_code TEXT,
  source_name TEXT NOT NULL,
  source_url TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT,
  published_at TEXT,
  fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  content_hash TEXT NOT NULL UNIQUE,
  is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS watchlists (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  crop_code TEXT NOT NULL,
  state_code TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, crop_code, state_code)
);

CREATE TABLE IF NOT EXISTS feed_refresh_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feed_name TEXT NOT NULL CHECK(feed_name IN ('weather', 'market', 'news')),
  source_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('healthy', 'degraded', 'failed')),
  requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  records_written INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_weather_location_time ON weather_observations(location_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_forecast_location_date ON weather_forecast_days(location_id, forecast_date);
CREATE INDEX IF NOT EXISTS idx_market_lookup ON market_observations(commodity_name, state_code, district, mandi_name, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_crop_time ON agriculture_news_items(crop_code, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlists(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_refresh_feed_time ON feed_refresh_logs(feed_name, requested_at DESC);
