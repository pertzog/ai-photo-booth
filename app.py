import base64
import json
import os
import queue
import random
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
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

with open(FILTERS_FILE, "r", encoding="utf-8") as f:
    FILTERS = json.load(f)


job_queue = queue.Queue()


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


worker_thread = threading.Thread(target=_process_ai_jobs, daemon=True)
worker_thread.start()


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
    job_queue.put(
        {
            "input_path": original_path,
            "output_path": ai_path,
            "prompt": prompt,
        }
    )

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
