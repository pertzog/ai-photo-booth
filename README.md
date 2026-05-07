# AI Photo Booth

## Spotify setup (optional)

If you want to enable Spotify-driven features, create a Spotify app in the
[Spotify Developer Dashboard](https://developer.spotify.com/dashboard), then copy the app credentials.

Recommended redirect URI for local Flask development:

- `http://localhost:5000/api/spotify/callback`

Add the following values to your `.env` file:

- `SPOTIFY_CLIENT_ID=...`
- `SPOTIFY_CLIENT_SECRET=...`
- `SPOTIFY_REDIRECT_URI=http://localhost:5000/api/spotify/callback`
- `SPOTIFY_SCOPES=user-read-playback-state user-read-currently-playing`
- `SPOTIFY_PLAYBACK_MODE=false` (default)

Playback mode is optional and adds complexity. Keep `SPOTIFY_PLAYBACK_MODE=false`
for display-only metadata mode, or set it to `true` to enable browser playback
via the Spotify Web Playback SDK.

When playback mode is enabled, add these scopes as needed:

- `streaming user-modify-playback-state user-read-email user-read-private`

> Note: Spotify Web Playback commonly requires a Spotify Premium account.

If these values are missing, the app logs a startup warning and continues
running so the slideshow and photo booth still work without Spotify.

## AI worker concurrency

The app processes OpenAI image edits in background worker threads.

- `AI_WORKER_COUNT=8` enables up to 8 concurrent OpenAI image-edit calls.
- Raising `AI_WORKER_COUNT` increases parallel API usage and can hit OpenAI rate limits faster.

## Optional queue backpressure

To prevent unbounded memory growth under heavy load, the queue size can be bounded:

- `AI_JOB_QUEUE_MAXSIZE=0` (default) keeps an unbounded queue.
- Set `AI_JOB_QUEUE_MAXSIZE` to a positive value to cap queued jobs.
- When the queue is full, `/api/capture` returns `503` with an error message.
