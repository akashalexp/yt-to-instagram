"""
downloader.py
Downloads a YouTube Shorts video, its thumbnail, and description using yt-dlp.
Returns local file paths and metadata.
"""

import os
import glob
import yt_dlp

DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def download_youtube_short(url: str) -> dict:
    """
    Download a YouTube Short (video + thumbnail) and return metadata.

    Returns a dict with keys:
        video_path     - absolute path to the downloaded .mp4 file
        thumbnail_path - absolute path to the thumbnail image (jpg/png/webp)
        caption        - video description (falls back to title)
        title          - video title
        video_id       - YouTube video ID

    On failure, returns {'error': '<message>'}.
    """
    ydl_opts = {
        # Prefer mp4; merge audio+video into mp4 when separate streams exist
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        # Save as <video_id>.mp4 inside downloads/
        "outtmpl": os.path.join(DOWNLOADS_DIR, "%(id)s.%(ext)s"),
        # Also download the thumbnail
        "writethumbnail": True,
        # Keep output quiet
        "quiet": True,
        "no_warnings": True,
        # Do not create .info.json files
        "writeinfojson": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        video_id = info.get("id", "")

        # --- Locate video file ---
        video_path = None
        for ext in ("mp4", "mkv", "webm"):
            candidate = os.path.join(DOWNLOADS_DIR, f"{video_id}.{ext}")
            if os.path.exists(candidate):
                video_path = candidate
                break

        if not video_path:
            # Fallback: glob for any file matching the id
            matches = glob.glob(os.path.join(DOWNLOADS_DIR, f"{video_id}.*"))
            video_matches = [m for m in matches if m.endswith((".mp4", ".mkv", ".webm"))]
            if video_matches:
                video_path = video_matches[0]

        if not video_path:
            return {"error": "Downloaded video file not found on disk."}

        # --- Locate thumbnail file ---
        thumbnail_path = None
        for ext in ("jpg", "jpeg", "png", "webp"):
            candidate = os.path.join(DOWNLOADS_DIR, f"{video_id}.{ext}")
            if os.path.exists(candidate):
                thumbnail_path = candidate
                break

        if not thumbnail_path:
            matches = glob.glob(os.path.join(DOWNLOADS_DIR, f"{video_id}.*"))
            img_matches = [m for m in matches if m.endswith((".jpg", ".jpeg", ".png", ".webp"))]
            if img_matches:
                thumbnail_path = img_matches[0]

        # --- Caption: prefer description, fall back to title ---
        description = (info.get("description") or "").strip()
        title = (info.get("title") or "").strip()
        caption = description if description else title

        return {
            "video_path": video_path,
            "thumbnail_path": thumbnail_path,  # may be None if not found
            "caption": caption,
            "title": title,
            "video_id": video_id,
        }

    except yt_dlp.utils.DownloadError as exc:
        return {"error": f"yt-dlp download error: {exc}"}
    except Exception as exc:
        return {"error": f"Unexpected error during download: {exc}"}


def cleanup_files(*paths):
    """Delete local files after upload is done."""
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
