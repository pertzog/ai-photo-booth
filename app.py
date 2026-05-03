import base64
import json
import os
import random
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


def _client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    return OpenAI(api_key=api_key)


def generate_ai_image(input_path: Path, output_path: Path, prompt: str):
    client = _client()
    with open(input_path, "rb") as image_file:
        image_b64 = base64.b64encode(image_file.read()).decode("utf-8")

    response = client.responses.create(
        model="gpt-image-1",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{image_b64}",
                    },
                ],
            }
        ],
    )

    image_data = None
    for output in response.output:
        for content in getattr(output, "content", []):
            if getattr(content, "type", None) == "output_image":
                image_data = content.image_base64
                break
        if image_data:
            break

    if not image_data:
        raise RuntimeError("No image returned from OpenAI")

    with open(output_path, "wb") as f:
        f.write(base64.b64decode(image_data))


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

    try:
        generate_ai_image(original_path, ai_path, prompt)
    except Exception as exc:
        return jsonify({"error": f"AI generation failed: {exc}"}), 500

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
