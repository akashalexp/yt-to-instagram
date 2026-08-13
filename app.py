"""
app.py
Flask web application — Upload a video and post it to Instagram Reels.

Routes:
  GET  /                  - Web UI
  POST /upload            - Accept video file + caption, post to Instagram
  GET  /media/<filename>  - Temporarily serve uploaded files for Instagram API
  GET  /health            - Health check
"""

import json
import os
import threading
import time
import uuid

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from downloader import DOWNLOADS_DIR, cleanup_files
from instagram_api import InstagramAPI, InstagramAPIError

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB max upload

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_url() -> str:
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        return render_url.rstrip("/")
    return "http://localhost:5050"


def _instagram_client() -> InstagramAPI:
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    user_id = os.getenv("INSTAGRAM_USER_ID")
    if not token or not user_id:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_USER_ID must be set in environment variables."
        )
    return InstagramAPI(access_token=token, ig_user_id=user_id)


def _public_url(filename: str) -> str:
    return f"{_base_url()}/media/{filename}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return {"status": "ok", "base_url": _base_url()}


@app.route("/media/<path:filename>")
def serve_media(filename):
    """Temporarily serve uploaded files so Instagram's API can fetch them."""
    return send_from_directory(DOWNLOADS_DIR, filename)


@app.route("/upload", methods=["POST"])
def upload():
    """
    Accept a video file + caption via multipart form upload.
    Save the file, post to Instagram, clean up, return JSON result.
    """
    video_path = None

    try:
        # --- Validate Instagram config ---
        try:
            ig = _instagram_client()
        except RuntimeError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

        # --- Validate file ---
        if "video" not in request.files:
            return jsonify({"success": False, "error": "No video file provided."}), 400

        video_file = request.files["video"]
        if not video_file.filename:
            return jsonify({"success": False, "error": "Empty filename."}), 400

        caption = request.form.get("caption", "").strip()

        # --- Save uploaded file ---
        ext = os.path.splitext(video_file.filename)[1].lower() or ".mp4"
        filename = f"upload_{uuid.uuid4().hex}{ext}"
        video_path = os.path.join(DOWNLOADS_DIR, filename)
        video_file.save(video_path)

        # --- Build public URL for Instagram to fetch from ---
        video_url = _public_url(filename)

        # --- Post to Instagram ---
        steps = []

        def progress(msg):
            steps.append({"message": msg, "type": "info"})

        progress(f"Video saved ({os.path.getsize(video_path) / 1024 / 1024:.1f} MB). Sending to Instagram...")
        published = ig.post_reel(
            video_url=video_url,
            caption=caption,
            cover_url=None,
            progress_callback=progress,
        )

        media_id = published.get("id", "")
        return jsonify({
            "success": True,
            "media_id": media_id,
            "caption": caption,
            "steps": steps,
        })

    except InstagramAPIError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"Unexpected error: {exc}"}), 500
    finally:
        # Give Instagram time to download before deleting
        def _cleanup():
            time.sleep(30)
            cleanup_files(video_path)
        if video_path:
            threading.Thread(target=_cleanup, daemon=True).start()


# ---------------------------------------------------------------------------
# Entry point (local dev only — Render uses gunicorn)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=False, port=5050, threaded=True)
