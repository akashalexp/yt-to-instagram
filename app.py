"""
app.py
Flask web application for the YouTube Shorts → Instagram Reels pipeline.

On Render, the app has a public URL so it can serve the downloaded video/thumbnail
directly to Instagram's API — no third-party file host (Cloudinary etc.) needed.

Routes:
  GET  /                      - Web UI
  GET  /post                  - SSE stream (real-time progress updates)
  GET  /media/<filename>      - Temporarily serves downloaded media files
  GET  /health                - Quick health check
"""

import json
import os
import queue
import threading
import time

from dotenv import load_dotenv
from flask import Flask, Response, render_template, request, send_from_directory, stream_with_context

from downloader import DOWNLOADS_DIR, cleanup_files, download_youtube_short
from instagram_api import InstagramAPI, InstagramAPIError

load_dotenv()

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_url() -> str:
    """
    Return the public base URL of this app.
    On Render, RENDER_EXTERNAL_URL is set automatically.
    Locally, falls back to http://localhost:5050
    """
    return os.getenv("RENDER_EXTERNAL_URL", "http://localhost:5050").rstrip("/")


def _instagram_client() -> InstagramAPI:
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    user_id = os.getenv("INSTAGRAM_USER_ID")
    if not token or not user_id:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_USER_ID must be set in environment variables."
        )
    return InstagramAPI(access_token=token, ig_user_id=user_id)


def _public_url(filename: str) -> str:
    """Build the public URL for a file served by this app."""
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
    """
    Temporarily serve downloaded media files so Instagram can fetch them.
    Files are deleted automatically after Instagram finishes processing.
    """
    return send_from_directory(DOWNLOADS_DIR, filename)


@app.route("/post")
def post_stream():
    """
    SSE endpoint — streams real-time progress to the browser.

    Query param:
        url  - YouTube Shorts URL to process

    Events emitted (JSON):
        { "step": "...", "message": "...", "type": "info|success|error" }
    """
    youtube_url = request.args.get("url", "").strip()

    def generate():
        msg_queue: queue.Queue = queue.Queue()

        def emit(step: str, message: str, event_type: str = "info"):
            payload = json.dumps({"step": step, "message": message, "type": event_type})
            msg_queue.put(f"data: {payload}\n\n")

        def emit_done(success: bool, extra: dict | None = None):
            payload = {"step": "done", "success": success}
            if extra:
                payload.update(extra)
            msg_queue.put(f"data: {json.dumps(payload)}\n\n")
            msg_queue.put(None)  # sentinel — tells generator to stop

        def run_pipeline():
            video_path = None
            thumbnail_path = None

            try:
                # --- Validate config ---
                try:
                    ig = _instagram_client()
                except RuntimeError as exc:
                    emit("config", str(exc), "error")
                    emit_done(False)
                    return

                if not youtube_url:
                    emit("input", "No URL provided.", "error")
                    emit_done(False)
                    return

                # --- Step 1: Download from YouTube ---
                emit("download", "Downloading video from YouTube...", "info")
                result = download_youtube_short(youtube_url)
                if "error" in result:
                    emit("download", result["error"], "error")
                    emit_done(False)
                    return

                video_path = result["video_path"]
                thumbnail_path = result["thumbnail_path"]
                caption = result["caption"]
                title = result["title"]
                emit("download", f'Downloaded: "{title}"', "info")

                # --- Step 2: Build public URLs (served by this app) ---
                video_filename = os.path.basename(video_path)
                video_url = _public_url(video_filename)

                cover_url = None
                if thumbnail_path:
                    thumb_filename = os.path.basename(thumbnail_path)
                    cover_url = _public_url(thumb_filename)

                emit("upload", f"Files ready at {_base_url()}", "info")

                # --- Step 3: Post to Instagram ---
                def ig_progress(msg):
                    emit("instagram", msg, "info")

                emit("instagram", "Sending to Instagram...", "info")
                published = ig.post_reel(
                    video_url=video_url,
                    caption=caption,
                    cover_url=cover_url,
                    progress_callback=ig_progress,
                )

                media_id = published.get("id", "")
                emit("instagram", f"Reel published! Media ID: {media_id}", "success")
                emit_done(True, {"media_id": media_id, "title": title, "caption": caption})

            except InstagramAPIError as exc:
                emit("instagram", str(exc), "error")
                emit_done(False)
            except Exception as exc:
                emit("error", f"Unexpected error: {exc}", "error")
                emit_done(False)
            finally:
                # Give Instagram a moment to finish downloading before we delete
                time.sleep(5)
                cleanup_files(video_path, thumbnail_path)

        # Run pipeline in a background thread so SSE can stream
        thread = threading.Thread(target=run_pipeline, daemon=True)
        thread.start()

        # Yield SSE messages as they arrive
        while True:
            try:
                item = msg_queue.get(timeout=660)  # matches gunicorn timeout
            except queue.Empty:
                yield 'data: {"step": "error", "message": "Pipeline timed out.", "type": "error"}\n\n'
                break
            if item is None:
                break
            yield item

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Prevents nginx from buffering SSE
        },
    )


# ---------------------------------------------------------------------------
# Entry point (local dev only — Render uses gunicorn)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5050, threaded=True)
