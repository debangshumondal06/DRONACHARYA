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