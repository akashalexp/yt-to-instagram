"""
instagram_api.py
Instagram Graph API client for posting Reels.

Flow:
  1. create_reel_container()  → creates a media container (Instagram fetches the video)
  2. wait_for_container()     → polls until status_code == FINISHED
  3. publish_container()      → makes the Reel live

Reference:
  https://developers.facebook.com/docs/instagram-api/reference/ig-user/media
  https://developers.facebook.com/docs/instagram-api/reference/ig-user/media_publish
"""

import os
import time
import requests

API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.instagram.com/{API_VERSION}"

# How long to wait for Instagram to process the video (seconds)
MAX_PROCESSING_WAIT = 600  # 10 minutes
POLL_INTERVAL = 10  # seconds between status checks


class InstagramAPIError(Exception):
    """Raised when the Instagram Graph API returns an error."""


class InstagramAPI:
    def __init__(self, access_token: str, ig_user_id: str):
        self.access_token = access_token
        self.ig_user_id = ig_user_id

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def post_reel(
        self,
        video_url: str,
        caption: str,
        cover_url: str | None = None,
        progress_callback=None,
    ) -> dict:
        """
        Full end-to-end flow: create container → wait → publish.

        Args:
            video_url:         Publicly accessible HTTPS URL of the .mp4 file.
            caption:           Post caption (hashtags included).
            cover_url:         Optional HTTPS URL of the cover/thumbnail image.
            progress_callback: Optional callable(message: str) for status updates.

        Returns:
            dict with 'id' (published media ID) on success.

        Raises:
            InstagramAPIError on any failure.
        """

        def _notify(msg):
            if progress_callback:
                progress_callback(msg)

        _notify("Creating Instagram media container...")
        container = self._create_reel_container(video_url, caption, cover_url)
        container_id = container["id"]
        _notify(f"Container created (ID: {container_id}). Waiting for Instagram to process video...")

        self._wait_for_container(container_id, progress_callback=_notify)

        _notify("Video processed. Publishing Reel...")
        result = self._publish_container(container_id)
        _notify(f"Reel published! Media ID: {result.get('id')}")
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_reel_container(
        self,
        video_url: str,
        caption: str,
        cover_url: str | None,
    ) -> dict:
        endpoint = f"{GRAPH_BASE}/{self.ig_user_id}/media"
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": self.access_token,
        }
        if cover_url:
            payload["cover_url"] = cover_url

        response = requests.post(endpoint, data=payload, timeout=30)
        self._raise_for_error(response)
        return response.json()

    def _wait_for_container(self, container_id: str, progress_callback=None) -> None:
        """Poll container status until FINISHED (or raise on ERROR/timeout)."""
        endpoint = f"{GRAPH_BASE}/{container_id}"
        params = {
            "fields": "status_code,status",
            "access_token": self.access_token,
        }
        deadline = time.time() + MAX_PROCESSING_WAIT
        attempt = 0

        while time.time() < deadline:
            response = requests.get(endpoint, params=params, timeout=30)
            self._raise_for_error(response)
            data = response.json()

            status_code = data.get("status_code", "")
            attempt += 1

            if status_code == "FINISHED":
                return
            elif status_code == "ERROR":
                detail = data.get("status", "unknown error")
                raise InstagramAPIError(f"Instagram container processing failed: {detail}")
            else:
                # IN_PROGRESS or unexpected — keep waiting
                elapsed = int(time.time() - (deadline - MAX_PROCESSING_WAIT))
                if progress_callback and attempt % 3 == 0:
                    progress_callback(
                        f"Still processing... ({elapsed}s elapsed, status: {status_code})"
                    )
                time.sleep(POLL_INTERVAL)

        raise InstagramAPIError(
            f"Timed out after {MAX_PROCESSING_WAIT}s waiting for Instagram to process the video."
        )

    def _publish_container(self, container_id: str) -> dict:
        endpoint = f"{GRAPH_BASE}/{self.ig_user_id}/media_publish"
        payload = {
            "creation_id": container_id,
            "access_token": self.access_token,
        }
        response = requests.post(endpoint, data=payload, timeout=30)
        self._raise_for_error(response)
        return response.json()

    @staticmethod
    def _raise_for_error(response: requests.Response) -> None:
        """Parse Instagram Graph API error responses and raise a descriptive exception."""
        try:
            body = response.json()
        except Exception:
            response.raise_for_status()
            return

        if "error" in body:
            err = body["error"]
            msg = err.get("message", str(err))
            code = err.get("code", "")
            raise InstagramAPIError(f"Graph API error {code}: {msg}")

        # Also catch non-2xx without a JSON error key
        if not response.ok:
            raise InstagramAPIError(f"HTTP {response.status_code}: {response.text[:300]}")
