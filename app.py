import os
import re
import sqlite3
from datetime import datetime

import fitz  # PyMuPDF
from flask import Flask, jsonify, render_template, request
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB

os.makedirs(app.instance_path, exist_ok=True)
DB_PATH = os.path.join(app.instance_path, "skillsync.db")

SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "c",
    "html", "css", "react", "node.js", "express", "flask", "django",
    "mongodb", "mysql", "sqlite", "postgresql", "sql", "git", "github",
    "docker", "aws", "azure", "machine learning", "deep learning",
    "artificial intelligence", "data structures", "algorithms",
    "rest api", "api", "bootstrap", "tailwind", "pandas", "numpy",
    "scikit-learn", "tensorflow", "pytorch", "linux", "oop",
    "problem solving", "data analysis", "computer networks",
    "operating systems", "backend development", "frontend development",
    "web development", "software development", "api development",
    "database management", "object oriented programming", "php",
    "java spring", "spring boot", "next.js", "vue", "angular",
    "figma", "postman", "redis", "kubernetes"
]

ALIASES = {
    "rest apis": "rest api",
    "restful api": "rest api",
    "restful apis": "rest api",
    "js": "javascript",
    "nodejs": "node.js",
    "scikit learn": "scikit-learn",
    "object-oriented programming": "object oriented programming",
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Applied',
                job_url TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_title TEXT NOT NULL,
                company TEXT NOT NULL,
                match_score INTEGER NOT NULL,
                text_similarity REAL NOT NULL,
                skill_score REAL NOT NULL,
                matched_skills TEXT NOT NULL,
                missing_skills TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


def extract_skills(text):
    text = text.lower()
    found = set()

    for skill in SKILLS:
        pattern = r"(?<![a-z0-9_])" + re.escape(skill) + r"(?![a-z0-9_])"
        if re.search(pattern, text):
            found.add(ALIASES.get(skill, skill))

    # Detect common variants that may be written with punctuation.
    if re.search(r"\brestful\s+apis?\b|\brest\s+apis?\b", text):
        found.add("rest api")
    if re.search(r"\bobject[- ]oriented programming\b", text):
        found.add("object oriented programming")

    return sorted(found)


def extract_resume_text(file):
    if file is None or not file.filename:
        raise ValueError("Please select a PDF resume.")

    if not file.filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF resumes are supported.")

    pdf_bytes = file.read()
    if not pdf_bytes:
        raise ValueError("The selected PDF is empty.")

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            if document.is_encrypted:
                raise ValueError("This PDF is password-protected. Upload an unlocked PDF.")
            text = "\n".join(page.get_text("text") for page in document)
        finally:
            document.close()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The PDF could not be read. Please try another PDF.") from exc

    if not text.strip():
        raise ValueError(
            "No readable text was found. Please upload a text-based PDF, not a scanned image."
        )
    return text


def calculate_match(resume_text, job_text):
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    try:
        matrix = vectorizer.fit_transform([resume_text, job_text])
        similarity = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
    except ValueError:
        similarity = 0.0

    resume_skills = set(extract_skills(resume_text))
    job_skills = set(extract_skills(job_text))
    matched = sorted(resume_skills & job_skills)
    missing = sorted(job_skills - resume_skills)

    if job_skills:
        skill_score = len(matched) / len(job_skills) * 100
        score = round((similarity * 100 * 0.4) + (skill_score * 0.6))
    else:
        # If no dictionary skills are detected in the job description,
        # avoid reporting a misleading zero skill-coverage score.
        skill_score = 0.0
        score = round(similarity * 100)

    suggestions = []
    if missing:
        suggestions.append(
            "The job description mentions these skills that were not detected "
            "in your resume: " + ", ".join(missing) +
            ". Learn and demonstrate them before adding them to your resume."
        )
    if similarity < 30:
        suggestions.append(
            "Review the job responsibilities and make relevant project or experience "
            "descriptions clearer. Do not copy the job description word-for-word."
        )
    if len(resume_skills) < 5:
        suggestions.append(
            "Consider adding a clearly labelled technical-skills section with tools "
            "and technologies you can genuinely use."
        )
    suggestions.append(
        "Prioritize relevant projects and describe your own contribution, the "
        "technologies used, and measurable results where you have real evidence."
    )

    return {
        "match_score": min(max(score, 0), 100),
        "text_similarity": round(similarity * 100, 2),
        "skill_score": round(skill_score, 2),
        "matched_skills": matched,
        "missing_skills": missing,
        "resume_skills": sorted(resume_skills),
        "job_skills": sorted(job_skills),
        "suggestions": suggestions
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        job_description = request.form.get("job_description", "").strip()
        if not job_description:
            return jsonify({"error": "Please enter a job description."}), 400
        if len(job_description) > 50000:
            return jsonify({"error": "Job description is too long (maximum 50,000 characters)."}), 400

        resume_text = extract_resume_text(request.files.get("resume"))
        result = calculate_match(resume_text, job_description)

        job_title = request.form.get("job_title", "").strip() or "Untitled Role"
        company = request.form.get("company", "").strip() or "Not specified"
        job_title = job_title[:150]
        company = company[:100]

        with get_db() as conn:
            cursor = conn.execute("""
                INSERT INTO analysis_history
                (job_title, company, match_score, text_similarity, skill_score,
                 matched_skills, missing_skills, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_title, company, result["match_score"],
                result["text_similarity"], result["skill_score"],
                ", ".join(result["matched_skills"]),
                ", ".join(result["missing_skills"]),
                datetime.now().isoformat(timespec="seconds")
            ))
            result["analysis_id"] = cursor.lastrowid

        return jsonify(result)

    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        app.logger.exception("Resume analysis failed")
        return jsonify({"error": "Analysis failed. Please check the PDF and try again."}), 500


ALLOWED_STATUSES = {"Applied", "Interview", "Selected", "Rejected"}


@app.route("/api/applications", methods=["GET"])
def get_applications():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM applications ORDER BY id DESC"
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/applications", methods=["POST"])
def add_application():
    data = request.get_json(silent=True) or {}
    company = str(data.get("company", "")).strip()
    role = str(data.get("role", "")).strip()
    status = str(data.get("status", "Applied")).strip()
    job_url = str(data.get("job_url", "")).strip()

    if not company or not role:
        return jsonify({"error": "Company and role are required."}), 400
    if status not in ALLOWED_STATUSES:
        return jsonify({"error": "Please choose a valid application status."}), 400
    if len(company) > 100 or len(role) > 150 or len(job_url) > 500:
        return jsonify({"error": "One or more fields are too long."}), 400

    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO applications (company, role, status, job_url, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            company, role, status, job_url,
            datetime.now().isoformat(timespec="seconds")
        ))
        new_id = cursor.lastrowid

    return jsonify({"message": "Application added.", "id": new_id}), 201


@app.route("/api/applications/<int:application_id>", methods=["PATCH"])
def update_application(application_id):
    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip()
    if status not in ALLOWED_STATUSES:
        return jsonify({"error": "Invalid application status."}), 400

    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE applications SET status = ? WHERE id = ?",
            (status, application_id)
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "Application not found."}), 404
    return jsonify({"message": "Application status updated."})


@app.route("/api/applications/<int:application_id>", methods=["DELETE"])
def delete_application(application_id):
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM applications WHERE id = ?",
            (application_id,)
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "Application not found."}), 404
    return jsonify({"message": "Application deleted."})


@app.route("/api/stats", methods=["GET"])
def get_stats():
    stats = {"total": 0, "Applied": 0, "Interview": 0, "Selected": 0, "Rejected": 0}
    with get_db() as conn:
        rows = conn.execute("""
            SELECT status, COUNT(*) AS total
            FROM applications GROUP BY status
        """).fetchall()

    for row in rows:
        stats[row["status"]] = row["total"]
        stats["total"] += row["total"]
    return jsonify(stats)


@app.route("/api/history", methods=["GET"])
def get_history():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM analysis_history ORDER BY id DESC LIMIT 50
        """).fetchall()
    return jsonify([dict(row) for row in rows])


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({"error": "File is too large. Maximum upload size is 5 MB."}), 413


init_db()

if __name__ == "__main__":
    app.run(debug=True)
