const emptyState = document.getElementById('emptyState');
const slide = document.getElementById('slide');
const spotifyConnectBtn = document.getElementById('spotifyConnectBtn');
const spotifyDisconnectBtn = document.getElementById('spotifyDisconnectBtn');
const spotifyPlayBtn = document.getElementById('spotifyPlayBtn');
const spotifyStatus = document.getElementById('spotifyStatus');
const trackInfo = document.getElementById('trackInfo');
const trackArt = document.getElementById('trackArt');
const trackMeta = document.getElementById('trackMeta');

let photos = [];
let current = 0;
let spotifyPlaybackMode = false;
let spotifyPlayer = null;
let spotifyDeviceId = null;

function setStatusText(text) {
  spotifyStatus.textContent = text;
}

function renderTrack(trackData) {
  const trackName = trackData?.name || trackData?.track || trackData?.title;
  const artist = trackData?.artist || trackData?.artists;
  const artUrl = trackData?.albumArtUrl || trackData?.album_art_url || trackData?.image;

  if (!trackName) {
    trackInfo.classList.add('hidden');
    trackMeta.textContent = '';
    trackArt.classList.add('hidden');
    trackArt.removeAttribute('src');
    return;
  }

  trackMeta.textContent = artist ? `${trackName} — ${artist}` : trackName;
  trackInfo.classList.remove('hidden');

  if (artUrl) {
    trackArt.src = artUrl;
    trackArt.classList.remove('hidden');
  } else {
    trackArt.classList.add('hidden');
    trackArt.removeAttribute('src');
  }
}

async function fetchSpotifyStatus() {
  try {
    const res = await fetch('/api/spotify/status');
    if (!res.ok) throw new Error('status failed');

    const data = await res.json();
    spotifyPlaybackMode = Boolean(data?.playback_mode);
    spotifyPlayBtn?.classList.toggle('hidden', !spotifyPlaybackMode || !data?.connected);

    if (!data?.connected) {
      setStatusText('Not connected');
      renderTrack(null);
      return;
    }

    if (data?.playing) {
      setStatusText('Playing …');
    } else if (data?.paused) {
      setStatusText('Paused');
    } else {
      setStatusText('No active track');
    }
  } catch {
    setStatusText('Not connected');
  }
}

function initSpotifyWebPlayback() {
  if (!spotifyPlaybackMode) {
    return;
  }
  if (!window.Spotify) {
    setStatusText('Spotify SDK not available');
    return;
  }
  if (spotifyPlayer) {
    return;
  }

  spotifyPlayer = new window.Spotify.Player({
    name: 'AI Photo Booth Slideshow',
    getOAuthToken: async (cb) => {
      const res = await fetch('/api/spotify/web-playback-token');
      if (!res.ok) {
        setStatusText('Unable to get playback token');
        return;
      }
      const data = await res.json();
      cb(data.access_token);
    },
    volume: 0.8,
  });

  spotifyPlayer.addListener('ready', ({ device_id }) => {
    spotifyDeviceId = device_id;
    setStatusText('Playback ready. Choose this device in Spotify.');
  });
  spotifyPlayer.addListener('not_ready', () => {
    setStatusText('Playback device offline');
  });
  spotifyPlayer.addListener('initialization_error', ({ message }) => {
    setStatusText(`Playback init failed: ${message}`);
  });
  spotifyPlayer.addListener('authentication_error', ({ message }) => {
    setStatusText(`Playback auth failed: ${message}`);
  });
  spotifyPlayer.addListener('account_error', ({ message }) => {
    setStatusText(`Playback requires Premium: ${message}`);
  });

  spotifyPlayer.connect();
}

async function fetchNowPlaying() {
  try {
    const res = await fetch('/api/spotify/now-playing');
    if (res.status === 204) {
      setStatusText('No active track');
      renderTrack(null);
      return;
    }
    if (!res.ok) throw new Error('now-playing failed');

    const data = await res.json();
    const isPlaying = Boolean(data?.isPlaying ?? data?.playing);
    const isConnected = data?.connected !== false;

    if (!isConnected) {
      setStatusText('Not connected');
      renderTrack(null);
      return;
    }

    if (data?.track || data?.name || data?.title) {
      setStatusText(isPlaying ? 'Playing …' : 'Paused');
      renderTrack(data);
    } else {
      setStatusText('No active track');
      renderTrack(null);
    }
  } catch {
    // keep previous UI state if endpoint is temporarily unavailable
  }
}

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

spotifyConnectBtn?.addEventListener('click', () => {
  window.location.href = '/api/spotify/login';
});

spotifyDisconnectBtn?.addEventListener('click', async () => {
  try {
    await fetch('/api/spotify/logout', { method: 'POST' });
  } finally {
    setStatusText('Not connected');
    renderTrack(null);
  }
});

spotifyPlayBtn?.addEventListener('click', () => {
  initSpotifyWebPlayback();
  if (spotifyDeviceId) {
    setStatusText('Playback enabled. Transfer playback in your Spotify app.');
  }
});

setInterval(fetchPhotos, 5000);
setInterval(rotate, 5000);
setInterval(fetchSpotifyStatus, 10000);
setInterval(fetchNowPlaying, 7000);

fetchPhotos().then(rotate);
fetchSpotifyStatus();
fetchNowPlaying();
