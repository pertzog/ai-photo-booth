const emptyState = document.getElementById('emptyState');
const slide = document.getElementById('slide');
const spotifyConnect = document.getElementById('spotifyConnect');
const spotifyPlay = document.getElementById('spotifyPlay');
const spotifyStop = document.getElementById('spotifyStop');
const spotifyStatus = document.getElementById('spotifyStatus');

let photos = [];
let current = 0;

let spotifyToken = null;
let spotifyPlayer = null;
let spotifyDeviceId = null;
let spotifyClientId = '';
let spotifyRedirectUri = '';

const spotifyScopes = [
  'streaming',
  'user-read-email',
  'user-read-private',
  'playlist-read-private',
  'user-modify-playback-state',
].join(' ');

async function fetchPhotos() {
  try {
    const res = await fetch('/api/photos');
    photos = await res.json();

    if (!photos.length) {
      emptyState.classList.remove('hidden');
      slide.classList.add('hidden');
      return;
    }

    emptyState.classList.add('hidden');
    slide.classList.remove('hidden');
  } catch {
    emptyState.textContent = 'Waiting for photos...';
  }
}

function rotate() {
  if (!photos.length) return;
  const photo = photos[current % photos.length];
  slide.src = `${photo.url}?t=${Date.now()}`;
  current += 1;
}

async function loadSpotifyConfig() {
  const res = await fetch('/api/spotify/config');
  const config = await res.json();
  spotifyClientId = config.client_id;
  spotifyRedirectUri = config.redirect_uri;

  if (!spotifyClientId) {
    spotifyStatus.textContent = 'Missing SPOTIFY_CLIENT_ID on server';
    return;
  }

  setStatus(`Spotify redirect URI: ${spotifyRedirectUri}`);
}

function setStatus(message) {
  spotifyStatus.textContent = message;
}

function setConnectedUi(connected) {
  spotifyConnect.classList.toggle('hidden', connected);
}

function base64UrlEncode(bytes) {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function randomVerifier(length = 64) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  const arr = new Uint8Array(length);
  crypto.getRandomValues(arr);
  return [...arr].map((b) => alphabet[b % alphabet.length]).join('');
}

async function challengeFromVerifier(verifier) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return base64UrlEncode(new Uint8Array(digest));
}

function loadStoredToken() {
  const accessToken = localStorage.getItem('spotify_access_token');
  const expiresAt = Number(localStorage.getItem('spotify_access_token_expires_at') || 0);

  if (!accessToken || !expiresAt || Date.now() >= expiresAt) {
    localStorage.removeItem('spotify_access_token');
    localStorage.removeItem('spotify_access_token_expires_at');
    return null;
  }

  return accessToken;
}

async function connectSpotify() {
  if (!spotifyClientId) {
    setStatus('Missing SPOTIFY_CLIENT_ID');
    return;
  }

  const verifier = randomVerifier();
  const challenge = await challengeFromVerifier(verifier);
  localStorage.setItem('spotify_pkce_verifier', verifier);

  const authUrl = new URL('https://accounts.spotify.com/authorize');
  authUrl.searchParams.set('client_id', spotifyClientId);
  authUrl.searchParams.set('response_type', 'code');
  authUrl.searchParams.set('redirect_uri', spotifyRedirectUri);
  authUrl.searchParams.set('scope', spotifyScopes);
  authUrl.searchParams.set('code_challenge_method', 'S256');
  authUrl.searchParams.set('code_challenge', challenge);
  window.location.href = authUrl.toString();
}

async function exchangeCodeForToken() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');
  const verifier = localStorage.getItem('spotify_pkce_verifier');

  if (!code) return;
  if (!verifier) {
    setStatus('Missing PKCE verifier; reconnect Spotify.');
    return;
  }

  const body = new URLSearchParams({
    client_id: spotifyClientId,
    grant_type: 'authorization_code',
    code,
    redirect_uri: spotifyRedirectUri,
    code_verifier: verifier,
  });

  const res = await fetch('https://accounts.spotify.com/api/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  if (!res.ok) {
    throw new Error('Token exchange failed');
  }

  const data = await res.json();
  const expiresAt = Date.now() + Number(data.expires_in || 0) * 1000;
  localStorage.setItem('spotify_access_token', data.access_token);
  localStorage.setItem('spotify_access_token_expires_at', String(expiresAt));
  localStorage.removeItem('spotify_pkce_verifier');
  window.history.replaceState({}, document.title, window.location.pathname);
}

function initWebPlaybackSdk() {
  return new Promise((resolve, reject) => {
    window.onSpotifyWebPlaybackSDKReady = () => {
      spotifyPlayer = new Spotify.Player({
        name: 'AI Photo Booth Slideshow Player',
        getOAuthToken: (cb) => cb(spotifyToken),
        volume: 0.5,
      });

      spotifyPlayer.addListener('ready', ({ device_id: deviceId }) => {
        spotifyDeviceId = deviceId;
        setStatus('Spotify connected');
        resolve();
      });

      spotifyPlayer.addListener('not_ready', () => {
        setStatus('Spotify player went offline');
      });

      spotifyPlayer.addListener('authentication_error', ({ message }) => {
        setStatus(`Spotify auth error: ${message}`);
      });

      spotifyPlayer.connect().catch(reject);
    };

    if (window.Spotify && !spotifyPlayer) {
      window.onSpotifyWebPlaybackSDKReady();
    }
  });
}

async function spotifyApi(path, options = {}) {
  const res = await fetch(`https://api.spotify.com/v1${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${spotifyToken}`,
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });

  if (!res.ok && res.status !== 204) {
    const errorBody = await res.text();
    throw new Error(errorBody || `Spotify API error (${res.status})`);
  }

  if (res.status === 204) return null;
  return res.json();
}

async function playFirstPlaylist() {
  if (!spotifyToken) {
    setStatus('Connect Spotify first');
    return;
  }

  if (!spotifyDeviceId) {
    await initWebPlaybackSdk();
  }

  const playlistData = await spotifyApi('/me/playlists?limit=1');
  const firstPlaylist = playlistData?.items?.[0];

  if (!firstPlaylist) {
    setStatus('No playlists found on your Spotify account');
    return;
  }

  await spotifyApi('/me/player', {
    method: 'PUT',
    body: JSON.stringify({ device_ids: [spotifyDeviceId], play: false }),
  });

  await spotifyApi('/me/player/play?device_id=' + encodeURIComponent(spotifyDeviceId), {
    method: 'PUT',
    body: JSON.stringify({ context_uri: firstPlaylist.uri }),
  });

  setStatus(`Playing: ${firstPlaylist.name}`);
}

async function stopPlayback() {
  if (!spotifyToken || !spotifyDeviceId) {
    setStatus('Nothing is playing');
    return;
  }

  await spotifyApi('/me/player/pause?device_id=' + encodeURIComponent(spotifyDeviceId), {
    method: 'PUT',
  });

  setStatus('Playback stopped');
}

setInterval(fetchPhotos, 5000);
setInterval(rotate, 5000);

fetchPhotos().then(rotate);
loadSpotifyConfig().then(() => {
  exchangeCodeForToken()
    .then(() => {
      spotifyToken = loadStoredToken();
      if (spotifyToken) {
        setConnectedUi(true);
        initWebPlaybackSdk().catch(() => setStatus('Failed to initialize Spotify player'));
      }
    })
    .catch(() => setStatus('Spotify login failed; please connect again.'));
});

spotifyConnect.addEventListener('click', () => {
  setStatus('Redirecting to Spotify...');
  connectSpotify().catch(() => setStatus('Failed to start Spotify login'));
});
spotifyPlay.addEventListener('click', () => {
  playFirstPlaylist().catch(() => setStatus('Failed to start playback'));
});
spotifyStop.addEventListener('click', () => {
  stopPlayback().catch(() => setStatus('Failed to stop playback'));
});
