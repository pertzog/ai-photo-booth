const emptyState = document.getElementById('emptyState');
const slide = document.getElementById('slide');
const spotifyPlayer = document.getElementById('spotifyPlayer');
const spotifyPlay = document.getElementById('spotifyPlay');
const spotifyStop = document.getElementById('spotifyStop');

const spotifyEmbedUrl = 'https://open.spotify.com/embed/playlist/37i9dQZF1DXcBWIGoYBM5M?utm_source=generator';

let photos = [];
let current = 0;

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

setInterval(fetchPhotos, 5000);
setInterval(rotate, 5000);

fetchPhotos().then(rotate);

spotifyPlay.addEventListener('click', () => {
  spotifyPlayer.src = `${spotifyEmbedUrl}&autoplay=1`;
});

spotifyStop.addEventListener('click', () => {
  spotifyPlayer.src = '';
});
