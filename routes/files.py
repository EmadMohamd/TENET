import os
from flask import (Blueprint, request, jsonify, render_template,
                   session, redirect, url_for, send_from_directory)
from werkzeug.utils import secure_filename

from config import UPLOAD_FOLDER
from middleware.auth import require_token

files_bp = Blueprint("files", __name__)


@files_bp.route("/uploads/")
@require_token(role="admin")
def uploads_list():
    if "username" not in session:
        return redirect(url_for("auth.login"))
    files = [
        f for f in os.listdir(UPLOAD_FOLDER)
        if os.path.isfile(os.path.join(UPLOAD_FOLDER, f))
    ]
    return render_template("uploads.html", files=files)


@files_bp.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    return f"[+] File {file.filename} successfully uploaded", 200


@files_bp.route("/uploads/<filename>", methods=["GET", "DELETE"])
def uploaded_file(filename):
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    if request.method == "GET":
        return send_from_directory(UPLOAD_FOLDER, filename)

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    try:
        os.remove(file_path)
        return jsonify({"message": "File deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@files_bp.route("/files-data")
def files_data():
    return jsonify(os.listdir(UPLOAD_FOLDER))