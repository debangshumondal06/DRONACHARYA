import hashlib
import json
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)
DATABASE_PATH = DATABASE_DIR / "dronacharya.db"
SCHEMA_PATH = DATABASE_DIR / "schema.sql"


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as connection:
        connection.executescript(schema)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(analyses)").fetchall()}
        if "user_id" not in columns:
            connection.execute("ALTER TABLE analyses ADD COLUMN user_id INTEGER")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)")
        connection.commit()


def _normalize_aadhaar(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 12:
        raise ValueError("Aadhaar number must contain exactly 12 digits.")
    if digits[0] == "0":
        raise ValueError("Please enter a valid Aadhaar number.")
    return digits


def _normalize_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError("Phone number must contain a valid 10-digit Indian mobile number.")
    return digits


def _normalize_email(value):
    email = (value or "").strip().lower()
    if not email:
        return None
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Please enter a valid email address or leave it blank.")
    return email


def _hash_value(value):
    # A server-side pepper makes the stored digest harder to use outside this application.
    pepper = "dronacharya-development-pepper-change-before-production"
    return hashlib.sha256(f"{pepper}:{value}".encode("utf-8")).hexdigest()


def find_or_create_user(aadhaar_number, phone_number, email_id=None):
    aadhaar = _normalize_aadhaar(aadhaar_number)
    phone = _normalize_phone(phone_number)
    email = _normalize_email(email_id)
    aadhaar_hash = _hash_value(aadhaar)
    phone_hash = _hash_value(phone)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE aadhaar_hash = ? AND phone_hash = ?",
            (aadhaar_hash, phone_hash),
        ).fetchone()

        if row is None:
            try:
                cursor = connection.execute(
                    """INSERT INTO users
                       (aadhaar_hash, phone_hash, aadhaar_last4, phone_last4, email, created_at, last_login_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (aadhaar_hash, phone_hash, aadhaar[-4:], phone[-4:], email, now, now),
                )
                user_id = cursor.lastrowid
            except sqlite3.IntegrityError as error:
                raise ValueError("This identity is already registered with another account combination.") from error
        else:
            user_id = row["id"]
            if email and row["email"] != email:
                connection.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))
            connection.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user_id))

        connection.commit()
        return {
            "id": user_id,
            "phone_last4": phone[-4:],
            "email": email,
        }


def get_user_by_id(user_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, aadhaar_last4, phone_last4, email, created_at, last_login_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def save_analysis(filename, report, prediction, recommendations, user_id=None):
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO analyses
               (filename, target_column, report_json, prediction_json, recommendations_json, user_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                filename,
                report.get("target_column"),
                json.dumps(report),
                json.dumps(prediction),
                json.dumps(recommendations),
                user_id,
            ),
        )
        connection.commit()
        return cursor.lastrowid


def get_analysis(analysis_id, user_id=None):
    query = "SELECT * FROM analyses WHERE id = ?"
    parameters = [analysis_id]
    if user_id is not None:
        query += " AND (user_id = ? OR user_id IS NULL)"
        parameters.append(user_id)

    with get_connection() as connection:
        row = connection.execute(query, parameters).fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "filename": row["filename"],
        "created_at": row["created_at"],
        "report": json.loads(row["report_json"]),
        "prediction": json.loads(row["prediction_json"]),
        "recommendations": json.loads(row["recommendations_json"]),
    }
