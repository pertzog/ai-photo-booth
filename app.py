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
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

BASE_DIR = Path(__file__).parent
PHOTOS_DIR = BASE_DIR / "photos"
ORIGINALS_DIR = PHOTOS_DIR / "originals"
AI_DIR = PHOTOS_DIR / "ai"
FINAL_DIR = PHOTOS_DIR / "final"
FILTERS_FILE = BASE_DIR / "filters.json"

ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
AI_DIR.mkdir(parents=True, exist_ok=True)
FINAL_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="/static")

with open(FILTERS_FILE, "r", encoding="utf-8") as f:
    FILTERS = json.load(f)


AI_WORKER_COUNT = max(1, min(32, int(os.getenv("AI_WORKER_COUNT", "8"))))
AI_JOB_QUEUE_MAXSIZE = max(0, int(os.getenv("AI_JOB_QUEUE_MAXSIZE", "0")))
job_queue = queue.Queue(maxsize=AI_JOB_QUEUE_MAXSIZE)


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






def _load_label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_candidates = [
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]

    for font_path in font_candidates:
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            continue

    return ImageFont.load_default()

def create_final_image(original_path: Path, ai_path: Path, final_path: Path):
    with Image.open(original_path) as original_img, Image.open(ai_path) as ai_img:
        original_img = original_img.convert("RGB")
        ai_img = ai_img.convert("RGB")

        target_height = max(original_img.height, ai_img.height)

        def _resize_to_height(img: Image.Image) -> Image.Image:
            if img.height == target_height:
                return img
            target_width = int(img.width * (target_height / img.height))
            return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

        original_img = _resize_to_height(original_img)
        ai_img = _resize_to_height(ai_img)

        label_band_height = 180
        combined_width = original_img.width + ai_img.width
        combined_height = target_height + label_band_height

        combined = Image.new("RGB", (combined_width, combined_height), color="black")
        combined.paste(original_img, (0, 0))
        combined.paste(ai_img, (original_img.width, 0))

        draw = ImageDraw.Draw(combined)
        label_text = "Omer B-Day 16/5/2026"

        max_text_width = int(combined_width * 0.96)
        max_text_height = int(label_band_height * 0.9)
        font_size = min(label_band_height, combined_width // 6)

        while font_size > 10:
            font = _load_label_font(font_size)
            if not hasattr(font, "size"):
                break

            text_bbox = draw.textbbox((0, 0), label_text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            if text_width <= max_text_width and text_height <= max_text_height:
                break
            font_size -= 2

        text_bbox = draw.textbbox((0, 0), label_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        label_x = (combined_width - text_width) // 2
        label_y = target_height + (label_band_height - text_height) // 2 - text_bbox[1]

        draw.text((label_x, label_y), label_text, fill="white", font=font)

        combined.save(final_path, format="PNG")

def _process_ai_jobs():
    while True:
        job = job_queue.get()
        try:
            generate_ai_image(job["input_path"], job["output_path"], job["prompt"])
        except Exception:
            shutil.copyfile(job["input_path"], job["output_path"])

        try:
            create_final_image(job["input_path"], job["output_path"], job["final_path"])
        except Exception:
            shutil.copyfile(job["output_path"], job["final_path"])
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


@app.route("/")
def booth_page():
    return app.send_static_file("booth.html")


@app.route("/slideshow")
def slideshow_page():
    return app.send_static_file("slideshow.html")


@app.route("/preview")
def preview_page():
    return app.send_static_file("preview.html")


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
    final_name = f"{timestamp}_final.png"

    original_path = ORIGINALS_DIR / original_name
    ai_path = AI_DIR / ai_name
    final_path = FINAL_DIR / final_name

    with open(original_path, "wb") as f:
        f.write(image_bytes)

    prompt = random.choice(FILTERS)
    job = {
        "input_path": original_path,
        "output_path": ai_path,
        "prompt": prompt,
        "final_path": final_path,
    }

    try:
        job_queue.put_nowait(job)
    except queue.Full:
        return jsonify({"error": "AI queue is full, try again shortly"}), 503

    return jsonify({"ok": True})


@app.get("/api/photos")
def get_photos():
    items = []
    for file_path in FINAL_DIR.glob("*_final.png"):
        created_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat()
        stem = file_path.name.removesuffix("_final.png")
        original_name = f"{stem}.png"
        ai_name = f"{stem}_ai.png"

        original_path = ORIGINALS_DIR / original_name
        ai_path = AI_DIR / ai_name

        if not original_path.exists() or not ai_path.exists():
            continue

        items.append(
            {
                "url": f"/photos/final/{file_path.name}",
                "original_url": f"/photos/originals/{original_name}",
                "ai_url": f"/photos/ai/{ai_name}",
                "created_at": created_at,
            }
        )

    items.sort(key=lambda x: x["created_at"])
    return jsonify(items)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
