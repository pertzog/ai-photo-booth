import base64
import json
import os
import queue
import random
import shutil
import threading
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory, session
from openai import OpenAI

load_dotenv()

BASE_DIR = Path(__file__).parent
PHOTOS_DIR = BASE_DIR / "photos"
ORIGINALS_DIR = PHOTOS_DIR / "originals"
AI_DIR = PHOTOS_DIR / "ai"
FILTERS_FILE = BASE_DIR / "filters.json"

ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
AI_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.urandom(32)

with open(FILTERS_FILE, "r", encoding="utf-8") as f:
    FILTERS = json.load(f)


AI_WORKER_COUNT = max(1, min(32, int(os.getenv("AI_WORKER_COUNT", "8"))))
AI_JOB_QUEUE_MAXSIZE = max(0, int(os.getenv("AI_JOB_QUEUE_MAXSIZE", "0")))
job_queue = queue.Queue(maxsize=AI_JOB_QUEUE_MAXSIZE)


def _load_spotify_config():
    config = {
        "client_id": os.getenv("SPOTIFY_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("SPOTIFY_CLIENT_SECRET", "").strip(),
        "redirect_uri": os.getenv("SPOTIFY_REDIRECT_URI", "").strip(),
        "scopes": os.getenv("SPOTIFY_SCOPES", "").strip(),
    }

    missing_keys = [key for key in ("client_id", "client_secret", "scopes") if not config[key]]
    if missing_keys:
        print(
            "[startup][warning] Spotify integration is disabled. "
            "Missing env var(s): "
            f"{', '.join(f'SPOTIFY_{key.upper()}' for key in missing_keys)}. "
            "Slideshow and photo booth will continue to run without Spotify."
        )
        return None

    print("[startup] Spotify integration is enabled.")
    if not config["redirect_uri"]:
        print(
            "[startup][warning] SPOTIFY_REDIRECT_URI is not set. "
            "Using request host fallback for OAuth redirect URI. "
            "Make sure that exact callback URL is added in the Spotify app settings."
        )
    return config


SPOTIFY_CONFIG = _load_spotify_config()
SPOTIFY_PLAYBACK_MODE = os.getenv("SPOTIFY_PLAYBACK_MODE", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    return OpenAI(api_key=api_key)


def generate_ai_image(input_path: Path, output_path: Path, prompt: str):
    client = _client()
    with open(input_path, "rb") as image_file:
        response = client.images.edit(
            model="gpt-image-1",
            image=image_file,
            prompt=prompt,
            size="1024x1024",
        )

    image_data = response.data[0].b64_json
    if not image_data:
        raise RuntimeError("No image returned from OpenAI Images API")

    with open(output_path, "wb") as f:
        f.write(base64.b64decode(image_data))


def _process_ai_jobs():
    while True:
        job = job_queue.get()
        try:
            generate_ai_image(job["input_path"], job["output_path"], job["prompt"])
        except Exception:
            shutil.copyfile(job["input_path"], job["output_path"])
        finally:
            job_queue.task_done()


worker_threads = []
for _ in range(AI_WORKER_COUNT):
    worker_thread = threading.Thread(target=_process_ai_jobs, daemon=True)
    worker_thread.start()
    worker_threads.append(worker_thread)

print(
    f"[startup] AI workers: {AI_WORKER_COUNT}; queue max size: "
    f"{'unbounded' if AI_JOB_QUEUE_MAXSIZE == 0 else AI_JOB_QUEUE_MAXSIZE}"
)


def _spotify_enabled():
    return SPOTIFY_CONFIG is not None


def _spotify_state_key():
    return "spotify_oauth_state"


def _spotify_redirect_uri_key():
    return "spotify_redirect_uri"


def _resolve_spotify_redirect_uri():
    configured = (SPOTIFY_CONFIG or {}).get("redirect_uri", "").strip()
    if configured:
        return configured
    return f"{request.url_root.rstrip('/')}/api/spotify/callback"


def spotify_token_expired():
    expires_at = session.get("spotify_expires_at")
    if not expires_at:
        return True

    try:
        expires_dt = datetime.fromisoformat(expires_at)
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True

    # Refresh slightly early to avoid race conditions around expiry.
    return datetime.now(timezone.utc) >= (expires_dt - timedelta(seconds=30))


def refresh_spotify_token(refresh_token):
    if not _spotify_enabled() or not refresh_token:
        return None

    token_data = urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": SPOTIFY_CONFIG["client_id"],
            "client_secret": SPOTIFY_CONFIG["client_secret"],
        }
    ).encode("utf-8")

    token_request = Request(
        "https://accounts.spotify.com/api/token",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    with urlopen(token_request, timeout=10) as resp:
        token_response = json.loads(resp.read().decode("utf-8"))

    access_token = token_response.get("access_token")
    if not access_token:
        return None

    expires_in = int(token_response.get("expires_in", 0))
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    session["spotify_access_token"] = access_token
    session["spotify_expires_at"] = expires_at

    new_refresh_token = token_response.get("refresh_token")
    if new_refresh_token:
        session["spotify_refresh_token"] = new_refresh_token

    return access_token


def get_valid_access_token():
    access_token = session.get("spotify_access_token")
    refresh_token = session.get("spotify_refresh_token")

    if not access_token and not refresh_token:
        return None

    if access_token and not spotify_token_expired():
        return access_token

    try:
        return refresh_spotify_token(refresh_token)
    except Exception:
        session.pop("spotify_access_token", None)
        session.pop("spotify_expires_at", None)
        return None


def _spotify_safe_error(message, status_code=502):
    return jsonify({"ok": False, "error": message}), status_code


def _spotify_api_get(path, access_token):
    api_request = Request(
        f"https://api.spotify.com/v1{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )

    try:
        with urlopen(api_request, timeout=10) as resp:
            status_code = getattr(resp, "status", resp.getcode())
            if status_code == 204:
                return {"ok": True, "status": 204, "data": None}
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body else None
            return {"ok": True, "status": status_code, "data": data}
    except HTTPError as e:
        if e.code == 204:
            return {"ok": True, "status": 204, "data": None}
        if e.code == 401:
            return {"ok": False, "status": 401, "message": "Spotify authorization expired"}
        if e.code == 403:
            return {"ok": False, "status": 403, "message": "Spotify access is not permitted for this account"}
        if e.code == 429:
            return {"ok": False, "status": 429, "message": "Spotify rate limit reached, please retry shortly"}
        return {"ok": False, "status": e.code, "message": "Spotify request failed"}
    except URLError:
        return {"ok": False, "status": 503, "message": "Spotify service is temporarily unavailable"}
    except Exception:
        return {"ok": False, "status": 500, "message": "Unexpected Spotify error"}


def _normalize_now_playing(playback_data):
    item = (playback_data or {}).get("item") or {}
    album = item.get("album") or {}
    images = album.get("images") or []
    artists = item.get("artists") or []

    return {
        "is_playing": bool((playback_data or {}).get("is_playing", False)),
        "track_name": item.get("name"),
        "artist_names": [artist.get("name") for artist in artists if artist.get("name")],
        "album_name": album.get("name"),
        "album_image_url": (images[0] or {}).get("url") if images else None,
        "progress_ms": (playback_data or {}).get("progress_ms"),
        "duration_ms": item.get("duration_ms"),
        "external_url": ((item.get("external_urls") or {}).get("spotify")),
    }


@app.get("/api/spotify/login")
def spotify_login():
    if not _spotify_enabled():
        return jsonify({"ok": False, "error": "Spotify integration is not configured"}), 503

    redirect_uri = _resolve_spotify_redirect_uri()
    state = secrets.token_urlsafe(24)
    session[_spotify_state_key()] = state
    session[_spotify_redirect_uri_key()] = redirect_uri

    params = {
        "response_type": "code",
        "client_id": SPOTIFY_CONFIG["client_id"],
        "redirect_uri": redirect_uri,
        "scope": SPOTIFY_CONFIG["scopes"],
        "state": state,
    }
    authorize_url = "https://accounts.spotify.com/authorize?" + urlencode(params)
    return redirect(authorize_url)


@app.get("/api/spotify/callback")
def spotify_callback():
    if not _spotify_enabled():
        return redirect("/slideshow")

    redirect_uri = session.get(_spotify_redirect_uri_key()) or _resolve_spotify_redirect_uri()
    session.pop(_spotify_redirect_uri_key(), None)

    request_state = request.args.get("state", "")
    expected_state = session.get(_spotify_state_key(), "")
    session.pop(_spotify_state_key(), None)

    if not request_state or not expected_state or request_state != expected_state:
        return redirect("/slideshow")

    code = request.args.get("code", "")
    if not code:
        return redirect("/slideshow")

    token_data = urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": SPOTIFY_CONFIG["client_id"],
            "client_secret": SPOTIFY_CONFIG["client_secret"],
        }
    ).encode("utf-8")

    try:
        token_request = Request(
            "https://accounts.spotify.com/api/token",
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(token_request, timeout=10) as resp:
            token_response = json.loads(resp.read().decode("utf-8"))

        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        expires_in = int(token_response.get("expires_in", 0))

        if access_token:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
            session["spotify_access_token"] = access_token
            if refresh_token:
                session["spotify_refresh_token"] = refresh_token
            session["spotify_expires_at"] = expires_at
    except Exception:
        pass

    return redirect("/slideshow")


@app.post("/api/spotify/logout")
def spotify_logout():
    session.pop(_spotify_state_key(), None)
    session.pop("spotify_access_token", None)
    session.pop("spotify_refresh_token", None)
    session.pop("spotify_expires_at", None)
    return jsonify({"ok": True})



@app.get("/api/spotify/status")
def spotify_status():
    if not _spotify_enabled():
        return jsonify({"connected": False, "configured": False, "playback_mode": False})

    access_token = get_valid_access_token()
    if not access_token:
        return jsonify(
            {"connected": False, "configured": True, "playback_mode": SPOTIFY_PLAYBACK_MODE}
        )

    profile_result = _spotify_api_get("/me", access_token)
    if not profile_result["ok"]:
        if profile_result["status"] == 401:
            session.pop("spotify_access_token", None)
            session.pop("spotify_expires_at", None)
            return jsonify(
                {
                    "connected": False,
                    "configured": True,
                    "playback_mode": SPOTIFY_PLAYBACK_MODE,
                }
            )
        return _spotify_safe_error(profile_result["message"], profile_result["status"])

    profile = profile_result.get("data") or {}
    return jsonify({
        "connected": True,
        "configured": True,
        "profile": {
            "id": profile.get("id"),
            "display_name": profile.get("display_name"),
            "product": profile.get("product"),
        },
        "playback_mode": SPOTIFY_PLAYBACK_MODE,
    })


@app.get("/api/spotify/web-playback-token")
def spotify_web_playback_token():
    if not _spotify_enabled():
        return jsonify({"ok": False, "error": "Spotify integration is not configured"}), 503
    if not SPOTIFY_PLAYBACK_MODE:
        return jsonify({"ok": False, "error": "Playback mode is disabled"}), 403

    access_token = get_valid_access_token()
    if not access_token:
        return jsonify({"ok": False, "error": "Spotify is not connected"}), 401

    return jsonify({"ok": True, "access_token": access_token})


@app.get("/api/spotify/now-playing")
def spotify_now_playing():
    if not _spotify_enabled():
        return jsonify({"connected": False})

    access_token = get_valid_access_token()
    if not access_token:
        return jsonify({"connected": False})

    playback_result = _spotify_api_get("/me/player/currently-playing", access_token)

    if not playback_result["ok"]:
        if playback_result["status"] == 401:
            session.pop("spotify_access_token", None)
            session.pop("spotify_expires_at", None)
            return jsonify({"connected": False})
        return _spotify_safe_error(playback_result["message"], playback_result["status"])

    if playback_result["status"] == 204 or not playback_result.get("data"):
        return jsonify({"connected": True, "is_playing": False})

    normalized = _normalize_now_playing(playback_result["data"])
    normalized["connected"] = True
    return jsonify(normalized)


@app.route("/")
def booth_page():
    return app.send_static_file("booth.html")


@app.route("/slideshow")
def slideshow_page():
    return app.send_static_file("slideshow.html")


@app.route("/photos/<path:filename>")
def photo_file(filename):
    return send_from_directory(PHOTOS_DIR, filename)


@app.post("/api/capture")
def capture_photo():
    data = request.get_json(silent=True) or {}
    image_base64 = data.get("image_base64", "")

    if not image_base64.startswith("data:image") or "," not in image_base64:
        return jsonify({"error": "Invalid image data"}), 400

    try:
        encoded = image_base64.split(",", 1)[1]
        image_bytes = base64.b64decode(encoded)
    except Exception:
        return jsonify({"error": "Cannot decode image"}), 400

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    original_name = f"{timestamp}.png"
    ai_name = f"{timestamp}_ai.png"

    original_path = ORIGINALS_DIR / original_name
    ai_path = AI_DIR / ai_name

    with open(original_path, "wb") as f:
        f.write(image_bytes)

    prompt = random.choice(FILTERS)
    job = {
        "input_path": original_path,
        "output_path": ai_path,
        "prompt": prompt,
    }

    try:
        job_queue.put_nowait(job)
    except queue.Full:
        return jsonify({"error": "AI queue is full, try again shortly"}), 503

    return jsonify({"ok": True})


@app.get("/api/photos")
def get_photos():
    items = []
    for file_path in AI_DIR.glob("*.png"):
        created_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat()
        items.append(
            {
                "url": f"/photos/ai/{file_path.name}",
                "created_at": created_at,
            }
        )

    items.sort(key=lambda x: x["created_at"])
    return jsonify(items)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
    redirect_uri = session.get(_spotify_redirect_uri_key()) or _resolve_spotify_redirect_uri()
    session.pop(_spotify_redirect_uri_key(), None)
