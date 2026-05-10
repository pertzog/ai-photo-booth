# AI Photo Booth

A lightweight Flask application for capturing webcam photos, applying AI-powered edits with OpenAI Images, and displaying results in a live slideshow.

## Overview

AI Photo Booth is designed for event-style experiences where users can take photos and quickly receive stylized AI versions. The app saves originals, queues AI edit jobs in the background, and serves generated images to a slideshow view.

## Key Features

- **Web capture flow** through a browser-based booth interface.
- **AI image editing pipeline** powered by `gpt-image-1`.
- **Background worker processing** with configurable concurrency.
- **Optional queue backpressure** to protect memory under high load.
- **Automatic fallback behavior** (copies original image) if AI processing fails.

## Project Structure

- `app.py` — Flask server, API routes, queue/worker management, and OpenAI image edit integration.
- `static/` — Frontend booth and slideshow pages, scripts, and styles.
- `filters.json` — Prompt list used to randomize AI edits.
- `photos/` — Runtime output directory for originals and AI-generated photos.

## Requirements

- Python 3.10+
- OpenAI API key with image-edit access

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Set environment variables before launching the app:

- `OPENAI_API_KEY` (required): API key used for OpenAI image generation.
- `AI_WORKER_COUNT` (optional, default `8`): Number of background workers processing AI jobs. Valid range is clamped between `1` and `32`.
- `AI_JOB_QUEUE_MAXSIZE` (optional, default `0`): Queue capacity.
  - `0` means unbounded queue.
  - Positive values cap pending jobs; when full, `/api/capture` returns HTTP `503`.

You can place variables in a `.env` file (loaded automatically via `python-dotenv`) or export them in your shell.

## Run Locally

```bash
python app.py
```

The app runs on `http://localhost:5000` by default.

## HTTP Endpoints

- `GET /` — Photo booth interface.
- `GET /slideshow` — Slideshow display page for AI photos.
- `POST /api/capture` — Accepts base64 image payload and enqueues AI processing.
- `GET /api/photos` — Returns generated AI photos with timestamps.
- `GET /photos/<path:filename>` — Serves stored photo assets.

## Operational Notes

- Increasing `AI_WORKER_COUNT` can improve throughput but may also increase OpenAI API rate-limit pressure.
- If a queued AI task fails, the app copies the original image into the AI output location so downstream slideshow display remains consistent.
- AI photos are returned in ascending creation order from `/api/photos`.

## License

Add your preferred license information here.
