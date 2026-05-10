const camera = document.getElementById('camera');
const canvas = document.getElementById('canvas');
const overlay = document.getElementById('overlay');
const captureBtn = document.getElementById('captureBtn');
const previewArea = document.getElementById('previewArea');
const preview = document.getElementById('preview');
const timerEl = document.getElementById('timer');
const keepBtn = document.getElementById('keepBtn');
const retakeBtn = document.getElementById('retakeBtn');
const successMsg = document.getElementById('successMsg');

let stream;
let capturedData = null;
let countdownTimer;

async function startCamera() {
  stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  camera.srcObject = stream;
}

function showCountdown() {
  return new Promise((resolve) => {
    let count = 3;
    overlay.textContent = count;
    const interval = setInterval(() => {
      count -= 1;
      if (count === 0) {
        clearInterval(interval);
        overlay.textContent = '';
        resolve();
      } else {
        overlay.textContent = count;
      }
    }, 1000);
  });
}

function captureFrame() {
  const w = camera.videoWidth;
  const h = camera.videoHeight;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.save();
  ctx.translate(w, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(camera, 0, 0, w, h);
  ctx.restore();
  return canvas.toDataURL('image/png');
}

function showPreview(dataUrl) {
  camera.classList.add('hidden');
  preview.src = dataUrl;
  previewArea.classList.remove('hidden');
  captureBtn.classList.add('hidden');

  let remaining = 5;
  timerEl.textContent = `${remaining}`;
  countdownTimer = setInterval(() => {
    remaining -= 1;
    timerEl.textContent = `${remaining}`;
    if (remaining <= 0) {
      clearInterval(countdownTimer);
      keepPhoto();
    }
  }, 1000);
}

function resetToCamera() {
  camera.classList.remove('hidden');
  previewArea.classList.add('hidden');
  successMsg.classList.add('hidden');
  captureBtn.classList.remove('hidden');
  timerEl.textContent = '';
  capturedData = null;
}

async function keepPhoto() {
  clearInterval(countdownTimer);
  if (!capturedData) return;

  keepBtn.disabled = true;
  retakeBtn.disabled = true;

  try {
    const res = await fetch('/api/capture', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_base64: capturedData }),
    });

    if (!res.ok) {
      throw new Error('failed');
    }

    previewArea.classList.add('hidden');
    successMsg.classList.remove('hidden');
    setTimeout(() => {
      keepBtn.disabled = false;
      retakeBtn.disabled = false;
      resetToCamera();
    }, 2500);
  } catch (e) {
    alert('שגיאה בשמירת התמונה');
    keepBtn.disabled = false;
    retakeBtn.disabled = false;
    resetToCamera();
  }
}

captureBtn.addEventListener('click', async () => {
  captureBtn.disabled = true;
  await showCountdown();
  capturedData = captureFrame();
  showPreview(capturedData);
  captureBtn.disabled = false;
});

keepBtn.addEventListener('click', keepPhoto);
retakeBtn.addEventListener('click', () => {
  clearInterval(countdownTimer);
  resetToCamera();
});

startCamera().catch(() => {
  alert('Unable to access camera');
});
