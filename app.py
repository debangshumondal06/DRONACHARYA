from pathlib import Path
import uuid

from flask import Flask, jsonify, redirect, render_template, request, url_for

from database import get_analysis, init_db, save_analysis
from data_cleaner import analyze_csv
from predictor import build_prediction
from recommender import build_recommendations

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {"csv"}

with app.app_context():
    init_db()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/dashboard")
def dashboard():
    return render_template("dashboard.html", analysis_id=request.args.get("analysis_id", ""))


@app.post("/api/upload")
def upload_dataset():
    uploaded_file = request.files.get("dataset")
    target_column = request.form.get("target_column", "").strip()

    if uploaded_file is None or uploaded_file.filename == "":
        return jsonify({"error": "Please select a CSV file before uploading."}), 400
    if not allowed_file(uploaded_file.filename):
        return jsonify({"error": "Only CSV files are supported in this first version."}), 400

    safe_name = uploaded_file.filename.replace(" ", "_")
    stored_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    uploaded_file.save(stored_path)

    try:
        report = analyze_csv(stored_path, target_column or None)
        prediction = build_prediction(report)
        recommendations = build_recommendations(report, prediction)
        analysis_id = save_analysis(uploaded_file.filename, report, prediction, recommendations)
        return jsonify({
            "message": "Dataset analyzed successfully.",
            "analysis_id": analysis_id,
            "redirect_url": url_for("dashboard", analysis_id=analysis_id),
        })
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.exception("Analysis failed")
        return jsonify({"error": f"Analysis failed: {error}"}), 500


@app.get("/api/analysis/<int:analysis_id>")
def analysis_result(analysis_id):
    analysis = get_analysis(analysis_id)
    if analysis is None:
        return jsonify({"error": "Analysis not found."}), 404
    return jsonify(analysis)


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "application": "DRONACHARYA"})


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "The file is too large. Please upload a CSV smaller than 10 MB."}), 413


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)

