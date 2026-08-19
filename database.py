import json
import sqlite3
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
        connection.commit()


def save_analysis(filename, report, prediction, recommendations):
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO analyses
               (filename, target_column, report_json, prediction_json, recommendations_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                filename,
                report.get("target_column"),
                json.dumps(report),
                json.dumps(prediction),
                json.dumps(recommendations),
            ),
        )
        connection.commit()
        return cursor.lastrowid


def get_analysis(analysis_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM analyses WHERE id = ?",
            (analysis_id,),
        ).fetchone()

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
