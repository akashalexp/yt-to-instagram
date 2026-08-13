"""
downloader.py
Downloads a YouTube Shorts video, its thumbnail, and description using yt-dlp.

Key design: no ffmpeg dependency.
  - Video:     uses a pre-merged mp4 stream (no ffmpeg merging needed)
  - Thumbnail: fetched directly from YouTube's CDN via requests
  - Auth:      uses YouTube cookies from YOUTUBE_COOKIES env var to bypass
               bot detection on cloud servers (Render, etc.)
"""

import os
import glob
import tempfile
import traceback
import requests
import yt_dlp

DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def _get_cookies_file():
    """
    Write YOUTUBE_COOKIES env var content to a temp file and return its path.
    Returns None if the env var is not set.
    """
    cookies_content = os.getenv("YOUTUBE_COOKIES", "").strip()
    if not cookies_content:
        return None
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="yt_cookies_"
    )
    tmp.write(cookies_content)
    tmp.close()
    return tmp.name


def download_youtube_short(url):
    """
    Download a YouTube Short (video + thumbnail) and return metadata.

    Returns a dict with keys:
        video_path     - absolute path to the downloaded video file
        thumbnail_path - absolute path to the thumbnail image (may be None)
        caption        - video description (falls back to title)
        title          - video title
        video_id       - YouTube video ID

    On failure, returns {'error': '<message>'}.
    """
    cookies_file = _get_cookies_file()

    ydl_opts = {
        "format": "best[ext=mp4]/best[ext=webm]/best",
        "outtmpl": os.path.join(DOWNLOADS_DIR, "%(id)s.%(ext)s"),
        "writethumbnail": False,
        "quiet": True,
        "no_warnings": True,
        "writeinfojson": False,
        "postprocessors": [],
    }

    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        video_id = info.get("id", "")

        # --- Locate downloaded video file ---
        video_path = None
        for ext in ("mp4", "webm", "mkv"):
            candidate = os.path.join(DOWNLOADS_DIR, f"{video_id}.{ext}")
            if os.path.exists(candidate):
                video_path = candidate
                break

        if not video_path:
            matches = glob.glob(os.path.join(DOWNLOADS_DIR, f"{video_id}.*"))
            video_matches = [
                m for m in matches
                if not m.endswith((".jpg", ".jpeg", ".png", ".webp", ".json"))
            ]
            if video_matches:
                video_path = video_matches[0]

        if not video_path:
            return {"error": "Downloaded video file not found on disk."}

        # --- Download thumbnail from YouTube CDN ---
        thumbnail_path = _download_thumbnail(info, video_id)

        # --- Caption: prefer description, fall back to title ---
        description = (info.get("description") or "").strip()
        title = (info.get("title") or "").strip()
        caption = description if description else title

        return {
            "video_path": video_path,
            "thumbnail_path": thumbnail_path,
            "caption": caption,
            "title": title,
            "video_id": video_id,
        }

    except yt_dlp.utils.DownloadError as exc:
        return {"error": f"yt-dlp download error: {exc}"}
    except Exception as exc:
        tb = traceback.format_exc()
        return {"error": f"Unexpected error during download: {exc}\n\nFull traceback:\n{tb}"}
    finally:
        # Clean up temp cookies file
        if cookies_file and os.path.exists(cookies_file):
            try:
                os.remove(cookies_file)
            except OSError:
                pass


def _download_thumbnail(info, video_id):
    """
    Download the best available thumbnail from YouTube directly using requests.
    Returns the local file path, or None if download fails (non-critical).
    """
    thumb_url = None

    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        def resolution(t):
            return (t.get("width") or 0) * (t.get("height") or 0)
        best = max(thumbnails, key=resolution)
        thumb_url = best.get("url")

    if not thumb_url:
        thumb_url = info.get("thumbnail")

    if not thumb_url:
        return None

    try:
        r = requests.get(thumb_url, timeout=15)
        if not r.ok:
            return None

        content_type = r.headers.get("Content-Type", "")
        if "webp" in content_type or thumb_url.endswith(".webp"):
            ext = "webp"
        elif "png" in content_type or thumb_url.endswith(".png"):
            ext = "png"
        else:
            ext = "jpg"

        thumb_path = os.path.join(DOWNLOADS_DIR, f"{video_id}.{ext}")
        with open(thumb_path, "wb") as f:
            f.write(r.content)

        return thumb_path

    except Exception:
        return None


def cleanup_files(*paths):
    """Delete local files after upload is done."""
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
