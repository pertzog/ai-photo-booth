const previewGrid = document.getElementById('previewGrid');
const previewEmptyState = document.getElementById('previewEmptyState');
const previewModal = document.getElementById('previewModal');
const previewModalImage = document.getElementById('previewModalImage');
const previewModalLabel = document.getElementById('previewModalLabel');
const previewCloseBtn = document.getElementById('previewCloseBtn');
const previewPrevBtn = document.getElementById('previewPrevBtn');
const previewNextBtn = document.getElementById('previewNextBtn');

let photoGroups = [];
let activeGroupIndex = -1;
let activeImageIndex = 0;
let swipeStartX = null;
let swipeStartY = null;
const swipeThreshold = 40;

const imageSteps = [
  { key: 'original_url', label: 'Original' },
  { key: 'ai_url', label: 'AI' },
  { key: 'url', label: 'Final' },
];

async function loadPhotos() {
  try {
    const res = await fetch('/api/photos');
    const items = await res.json();
    photoGroups = items.filter((item) => item.original_url && item.ai_url && item.url);

    renderGrid();
  } catch {
    previewEmptyState.textContent = 'Unable to load photos right now.';
    previewEmptyState.classList.remove('hidden');
  }
}

function renderGrid() {
  previewGrid.innerHTML = '';

  if (!photoGroups.length) {
    previewEmptyState.classList.remove('hidden');
    return;
  }

  previewEmptyState.classList.add('hidden');

  photoGroups
    .slice()
    .reverse()
    .forEach((group, idxFromEnd) => {
      const actualIndex = photoGroups.length - 1 - idxFromEnd;
      const btn = document.createElement('button');
      btn.className = 'thumb-btn';
      btn.type = 'button';
      btn.innerHTML = `<img src="${group.url}" alt="Final thumbnail" loading="lazy" />`;
      btn.addEventListener('click', () => openModal(actualIndex, 2));
      previewGrid.appendChild(btn);
    });
}

function updateModalImage() {
  if (activeGroupIndex < 0) return;
  const activeGroup = photoGroups[activeGroupIndex];
  const step = imageSteps[activeImageIndex];
  previewModalImage.src = activeGroup[step.key];
  previewModalLabel.textContent = `${step.label} (${activeImageIndex + 1}/3)`;
}

function openModal(groupIndex, imageIndex) {
  activeGroupIndex = groupIndex;
  activeImageIndex = imageIndex;
  previewModal.classList.remove('hidden');
  updateModalImage();
}

function closeModal() {
  previewModal.classList.add('hidden');
  activeGroupIndex = -1;
}

function showNext() {
  activeImageIndex = (activeImageIndex + 1) % imageSteps.length;
  updateModalImage();
}

function showPrev() {
  activeImageIndex = (activeImageIndex - 1 + imageSteps.length) % imageSteps.length;
  updateModalImage();
}

previewNextBtn.addEventListener('click', showNext);
previewPrevBtn.addEventListener('click', showPrev);
previewCloseBtn.addEventListener('click', closeModal);

previewModal.addEventListener('click', (event) => {
  if (event.target === previewModal) closeModal();
});

previewModal.addEventListener(
  'touchstart',
  (event) => {
    if (previewModal.classList.contains('hidden') || event.touches.length !== 1) return;
    swipeStartX = event.touches[0].clientX;
    swipeStartY = event.touches[0].clientY;
  },
  { passive: true }
);

previewModal.addEventListener(
  'touchend',
  (event) => {
    if (previewModal.classList.contains('hidden') || swipeStartX === null || swipeStartY === null) return;
    if (event.changedTouches.length !== 1) return;

    const endX = event.changedTouches[0].clientX;
    const endY = event.changedTouches[0].clientY;
    const deltaX = endX - swipeStartX;
    const deltaY = endY - swipeStartY;

    swipeStartX = null;
    swipeStartY = null;

    if (Math.abs(deltaX) < swipeThreshold || Math.abs(deltaX) < Math.abs(deltaY)) return;

    if (deltaX < 0) {
      showNext();
      return;
    }
    showPrev();
  },
  { passive: true }
);

document.addEventListener('keydown', (event) => {
  if (previewModal.classList.contains('hidden')) return;

  if (event.key === 'Escape') closeModal();
  if (event.key === 'ArrowRight') showNext();
  if (event.key === 'ArrowLeft') showPrev();
});

loadPhotos();
