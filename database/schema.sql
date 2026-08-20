CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aadhaar_hash TEXT NOT NULL,
    phone_hash TEXT NOT NULL,
    aadhaar_last4 TEXT NOT NULL,
    phone_last4 TEXT NOT NULL,
    email TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(aadhaar_hash, phone_hash)
);

CREATE INDEX IF NOT EXISTS idx_users_phone_hash ON users(phone_hash);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    target_column TEXT,
    report_json TEXT NOT NULL,
    prediction_json TEXT NOT NULL,
    recommendations_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at);
