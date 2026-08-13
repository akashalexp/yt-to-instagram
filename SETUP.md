# Setup Guide

This guide walks you through credentials setup and deploying to Render.

---

## Prerequisites

- A [GitHub](https://github.com) account (to connect to Render)
- A [Render](https://render.com) account (free)
- An Instagram **Business** or **Creator** account linked to a Facebook Page

---

## 1. Get your Instagram credentials

### 1a. Create a Facebook Developer App

1. Go to [developers.facebook.com](https://developers.facebook.com) and log in.
2. Click **My Apps** → **Create App** → select **Business** → Continue.
3. Give it a name (e.g. `yt-to-instagram`) → Create App.

### 1b. Get your Instagram User ID

1. Open the [Graph API Explorer](https://developers.facebook.com/tools/explorer).
2. Select your app from the top-right dropdown.
3. Select the Facebook Page connected to your Instagram account.
4. Run this query:
   ```
   GET /me?fields=instagram_business_account
   ```
5. Copy the numeric `id` from `instagram_business_account` — this is your **Instagram User ID**.

### 1c. Generate a Page Access Token

1. Still in the Graph API Explorer, click **Generate Access Token**.
2. Grant these permissions: `instagram_content_publish`, `instagram_basic`, `pages_read_engagement`.
3. Copy the short-lived token shown.

### 1d. Exchange for a long-lived token (valid 60 days)

Run this in your terminal (replace placeholders):

```bash
curl "https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=SHORT_LIVED_TOKEN"
```

Copy the `access_token` from the response.

> Refresh before it expires by repeating this step with the existing long-lived token as `fb_exchange_token`.

---

## 2. Push the project to GitHub

```bash
cd yt-to-instagram
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/yt-to-instagram.git
git push -u origin main
```

---

## 3. Deploy to Render

1. Go to [render.com](https://render.com) → **New** → **Web Service**.
2. Connect your GitHub account and select the `yt-to-instagram` repository.
3. Render will auto-detect `render.yaml` and pre-fill the settings:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app --bind 0.0.0.0:$PORT --worker-class gevent --workers 2 --timeout 660 --keep-alive 660`
4. Under **Environment Variables**, add:

   | Key | Value |
   |---|---|
   | `INSTAGRAM_ACCESS_TOKEN` | your long-lived token from step 1d |
   | `INSTAGRAM_USER_ID` | your numeric user ID from step 1b |

5. Click **Deploy**. Render will install dependencies and start the app.
6. Once deployed, your app URL will be something like:
   ```
   https://yt-to-instagram.onrender.com
   ```

> Render sets `RENDER_EXTERNAL_URL` automatically — the app uses this to build public file URLs for Instagram's API. You don't need to set it manually.

---

## 4. Use the app

1. Open your Render URL in a browser.
2. Wait ~50 seconds if the app was sleeping (free tier cold start).
3. Paste a YouTube Shorts URL → click **Post to Instagram**.
4. Watch the real-time progress log. Done!

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `yt-dlp` download fails | The yt-dlp version may be outdated — add `yt-dlp --update` to build command |
| `Graph API error 10: Permission denied` | Re-generate token with correct permissions (step 1c) |
| `Graph API error 100: Invalid parameter` | Check that `RENDER_EXTERNAL_URL` is accessible — visit `/health` to confirm |
| Token expired | Repeat step 1c–1d; update the env var in Render dashboard |
| App sleeping on free tier | Wait ~50s for cold start, or upgrade to Render's $7/month paid tier |
| Video stuck processing | Instagram can take up to 5 minutes for longer videos; the app waits up to 10 min |

---

## Token refresh reminder

Long-lived tokens expire after **60 days**. Set a calendar reminder to refresh yours by repeating step 1d, then update the `INSTAGRAM_ACCESS_TOKEN` value in your Render dashboard under **Environment**.
