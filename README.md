# AI Photo Booth

## AI worker concurrency

The app processes OpenAI image edits in background worker threads.

- `AI_WORKER_COUNT=8` enables up to 8 concurrent OpenAI image-edit calls.
- Raising `AI_WORKER_COUNT` increases parallel API usage and can hit OpenAI rate limits faster.

## Optional queue backpressure

To prevent unbounded memory growth under heavy load, the queue size can be bounded:

- `AI_JOB_QUEUE_MAXSIZE=0` (default) keeps an unbounded queue.
- Set `AI_JOB_QUEUE_MAXSIZE` to a positive value to cap queued jobs.
- When the queue is full, `/api/capture` returns `503` with an error message.

## Spotify Premium slideshow playback

To play your own Spotify playlists from the slideshow page:

- Set `SPOTIFY_CLIENT_ID` in your environment.
- In Spotify Developer Dashboard, add `http://localhost:5000/slideshow` (or your deployed URL) as a Redirect URI.
- Open `/slideshow`, click **Connect Spotify**, authorize your Premium account, then use **Play** and **Stop**.

The slideshow Play button starts your first playlist from your Spotify account.
