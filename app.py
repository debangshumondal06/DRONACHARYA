import os
import uuid
import json
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from database import (
    find_or_create_user,
    get_analysis,
    get_user_by_id,
    get_connection,
    init_db,
    save_analysis,
)
from data_cleaner import analyze_csv
from predictor import build_prediction
from recommender import build_recommendations
from yield_backend import init_db as init_yield_db
from yield_backend import yield_bp
from marketplace_backend import marketplace_bp

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
secret_key = os.getenv("DRONACHARYA_SECRET_KEY")
if not secret_key:
    raise RuntimeError(
        "DRONACHARYA_SECRET_KEY must be set before starting the application."
    )
app.config["SECRET_KEY"] = secret_key

ALLOWED_EXTENSIONS = {"csv"}

# The yield blueprint supplies /api/estimate and /api/history routes.
# Its duplicate page route is removed in Section 5 below.
app.register_blueprint(yield_bp)
app.register_blueprint(marketplace_bp)

with app.app_context():
    init_db()
    init_yield_db()


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify(
                    {"error": "Please log in before using this feature."}
                ), 401
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)

    return wrapped_view


@app.get("/login", endpoint="login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("home"))
    return render_template("login.html")


@app.post("/api/auth/login")
def login_api():
    if request.form.get("prototype_consent") != "true":
        return jsonify(
            {"error": "Prototype consent is required before continuing."}
        ), 400

    aadhaar_number = request.form.get("aadhaar_number", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    email_id = request.form.get("email_id", "").strip()

    try:
        user = find_or_create_user(aadhaar_number, phone_number, email_id)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    session.clear()
    session["user_id"] = user["id"]
    session["phone_last4"] = user["phone_last4"]
    session.permanent = True

    return jsonify(
        {
            "message": "Login successful.",
            "redirect_url": url_for("home"),
        }
    )


@app.post("/api/auth/logout")
def logout_api():
    session.clear()
    return jsonify(
        {
            "message": "Logged out successfully.",
            "redirect_url": url_for("login"),
        }
    )


@app.get("/")
@login_required
def home():
    return render_template("index.html")


@app.get("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        analysis_id=request.args.get("analysis_id", ""),
    )


@app.get("/estimate-yield", endpoint="estimate_yield")
def estimate_yield_page():
    return render_template("estimate_yield.html")


@app.get("/field-visit", endpoint="field_visit")
@login_required
def field_visit_page():
    return render_template("field_visit.html")


@app.get("/store", endpoint="store")
@login_required
def store_page():
    return render_template("store.html")


@app.get("/assistant", endpoint="assistant")
def assistant_page():
    return render_template("assistant.html")


@app.post("/api/upload")
@login_required
def upload_dataset():
    uploaded_file = request.files.get("dataset")
    target_column = request.form.get("target_column", "").strip()

    if uploaded_file is None or uploaded_file.filename == "":
        return jsonify(
            {"error": "Please select a CSV file before uploading."}
        ), 400

    if not allowed_file(uploaded_file.filename):
        return jsonify(
            {"error": "Only CSV files are supported in this first version."}
        ), 400

    original_filename = uploaded_file.filename
    safe_name = secure_filename(original_filename) or "dataset.csv"
    stored_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    uploaded_file.save(stored_path)

    try:
        report = analyze_csv(stored_path, target_column or None)
        prediction = build_prediction(report)
        recommendations = build_recommendations(report, prediction)
        analysis_id = save_analysis(
            original_filename,
            report,
            prediction,
            recommendations,
            user_id=session["user_id"],
        )
        return jsonify(
            {
                "message": "Dataset analyzed successfully.",
                "analysis_id": analysis_id,
                "redirect_url": url_for(
                    "dashboard",
                    analysis_id=analysis_id,
                ),
            }
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        app.logger.exception("Analysis failed")
        return jsonify(
            {"error": "Analysis failed. Please check the CSV and try again."}
        ), 500
    finally:
        stored_path.unlink(missing_ok=True)


@app.get("/api/analysis/<int:analysis_id>")
@login_required
def analysis_result(analysis_id):
    analysis = get_analysis(analysis_id, user_id=session["user_id"])
    if analysis is None:
        return jsonify(
            {"error": "Analysis not found or unavailable for this account."}
        ), 404
    return jsonify(analysis)


@app.get("/api/auth/me")
@login_required
def current_user():
    user = get_user_by_id(session["user_id"])
    if user is None:
        session.clear()
        return jsonify({"error": "Session expired."}), 401
    return jsonify(user)


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "application": "DRONACHARYA"})


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify(
        {"error": "The file is too large. Please upload a CSV smaller than 10 MB."}
    ), 413

@app.post("/api/field-visits")
@login_required
def create_field_visit():
    payload = request.get_json(silent=True) or {}
    required = ("fieldName", "phone", "visitDate")
    missing = [
        name
        for name in required
        if not str(payload.get(name, "")).strip()
    ]
    tests = payload.get("tests") or []

    if missing:
        return jsonify(
            {"error": f"Missing fields: {', '.join(missing)}"}
        ), 400

    if not tests:
        return jsonify(
            {"error": "Select at least one diagnostic test."}
        ), 400

    request_code = f"DRV-{uuid.uuid4().hex[:8].upper()}"

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO field_visits (
                request_code,
                user_id,
                payload_json,
                status
            ) VALUES (?, ?, ?, 'submitted')
            """,
            (
                request_code,
                session["user_id"],
                json.dumps(payload),
            ),
        )
        connection.commit()

    return jsonify(
        {
            "request_code": request_code,
            "status": "submitted",
            "message": "Field visit request submitted for review.",
        }
    ), 201

if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
    )