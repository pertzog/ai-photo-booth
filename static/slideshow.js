const emptyState = document.getElementById('emptyState');
const slide = document.getElementById('slide');
const spotifyConnectBtn = document.getElementById('spotifyConnectBtn');
const spotifyDisconnectBtn = document.getElementById('spotifyDisconnectBtn');
const spotifyStatus = document.getElementById('spotifyStatus');
const trackInfo = document.getElementById('trackInfo');
const trackArt = document.getElementById('trackArt');
const trackMeta = document.getElementById('trackMeta');

let photos = [];
let current = 0;

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

setInterval(fetchPhotos, 5000);
setInterval(rotate, 5000);
setInterval(fetchSpotifyStatus, 10000);
setInterval(fetchNowPlaying, 7000);

fetchPhotos().then(rotate);
fetchSpotifyStatus();
fetchNowPlaying();
