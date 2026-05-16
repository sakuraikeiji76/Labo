// ── Landmark indices ──────────────────────────────────────────────────────────
const OUTER_INDICES = [0,267,269,270,409,291,375,321,405,314,17,84,181,91,146,61,185,40,39,37];
const INNER_INDICES = [78,95,88,178,87,14,317,402,318,324,308,415,310,311,312,13,82,81,80,191];
const ALL_LIP_INDICES = [...OUTER_INDICES, ...INNER_INDICES];

// ── DOM refs ─────────────────────────────────────────────────────────────────
const video        = document.getElementById('video');
const canvas       = document.getElementById('canvas');
const ctx          = canvas.getContext('2d');
const mouthCanvas  = document.getElementById('mouth-canvas');
const mctx         = mouthCanvas.getContext('2d');
const statusBadge  = document.getElementById('status-badge');
const fpsOverlay   = document.getElementById('fps-overlay');
const btnCamera    = document.getElementById('btn-camera');
const btnRecord    = document.getElementById('btn-record');
const phraseInput  = document.getElementById('phrase-label');
const mOpenness    = document.getElementById('m-openness');
const mWidth       = document.getElementById('m-width');
const mRatio       = document.getElementById('m-ratio');
const mFps         = document.getElementById('m-fps');

// ── State ─────────────────────────────────────────────────────────────────────
let faceMesh = null;
let cameraRunning = false;
let recording = false;
let recordedFrames = [];
let recordStart = 0;

// FPS tracking
let frameTimes = [];
let lastFps = 0;

// ── Utility ───────────────────────────────────────────────────────────────────
function setStatus(mode) {
  statusBadge.className = `badge badge-${mode}`;
  const labels = { idle: '待機中', running: '検出中', rec: '録画中' };
  statusBadge.textContent = labels[mode] ?? mode;
}

function calcFps() {
  const now = performance.now();
  frameTimes.push(now);
  // keep only last 1 second
  const cutoff = now - 1000;
  frameTimes = frameTimes.filter(t => t > cutoff);
  return frameTimes.length;
}

function downloadJSON(obj, filename) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Drawing helpers ───────────────────────────────────────────────────────────
/**
 * Draw dots + index labels for a set of landmark indices.
 * landmarks: normalized coords array from FaceMesh results
 */
function drawLipGroup(landmarks, indices, color, scaleX, scaleY) {
  ctx.fillStyle = color;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.font = 'bold 9px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  // Draw outline polyline
  ctx.beginPath();
  indices.forEach((idx, i) => {
    const lm = landmarks[idx];
    // canvas is drawn mirrored via ctx.scale(-1,1) so x is already flipped
    const x = lm.x * scaleX;
    const y = lm.y * scaleY;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.globalAlpha = 0.55;
  ctx.stroke();
  ctx.globalAlpha = 1;

  // Draw dots + labels
  indices.forEach(idx => {
    const lm = landmarks[idx];
    const x = lm.x * scaleX;
    const y = lm.y * scaleY;
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();

    // label background
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.fillRect(x - 7, y - 17, 14, 11);
    ctx.fillStyle = color;
    ctx.fillText(String(idx), x, y - 11);
  });
}

/**
 * Draw mouth shape viewer on the side panel canvas.
 * Normalizes the 40 points to fit the canvas.
 */
function drawMouthViewer(landmarks) {
  const pts = ALL_LIP_INDICES.map(i => landmarks[i]);
  if (!pts.length) return;

  const xs = pts.map(p => p.x);
  const ys = pts.map(p => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;

  const W = mouthCanvas.width;
  const H = mouthCanvas.height;
  const pad = 24;

  mctx.clearRect(0, 0, W, H);
  mctx.fillStyle = '#0f172a';
  mctx.fillRect(0, 0, W, H);

  function norm(p) {
    return {
      x: W - pad - ((p.x - minX) / rangeX) * (W - pad * 2),  // mirror
      y: pad + ((p.y - minY) / rangeY) * (H - pad * 2)
    };
  }

  function drawGroup(indices, color) {
    mctx.fillStyle = color;
    mctx.strokeStyle = color;
    mctx.lineWidth = 1.8;

    mctx.beginPath();
    indices.forEach((idx, i) => {
      const n = norm(landmarks[idx]);
      if (i === 0) mctx.moveTo(n.x, n.y); else mctx.lineTo(n.x, n.y);
    });
    mctx.closePath();
    mctx.globalAlpha = 0.5;
    mctx.stroke();
    mctx.globalAlpha = 1;

    indices.forEach(idx => {
      const n = norm(landmarks[idx]);
      mctx.beginPath();
      mctx.arc(n.x, n.y, 3, 0, Math.PI * 2);
      mctx.fill();
    });
  }

  drawGroup(OUTER_INDICES, '#22c55e');
  drawGroup(INNER_INDICES, '#f97316');
}

/**
 * Compute metrics from landmarks.
 * Returns { openness, width, ratio } in normalized units (0–1).
 */
function computeMetrics(landmarks) {
  // Mouth height: top-inner(13) to bottom-inner(14)
  const top    = landmarks[13];
  const bottom = landmarks[14];
  const left   = landmarks[61];
  const right  = landmarks[291];

  const height = Math.hypot(top.x - bottom.x, top.y - bottom.y);
  const width  = Math.hypot(left.x - right.x, left.y - right.y);
  const ratio  = width > 0 ? height / width : 0;

  return { openness: height, width, ratio };
}

// ── FaceMesh callback ─────────────────────────────────────────────────────────
function onResults(results) {
  const W = canvas.width;
  const H = canvas.height;

  // Clear and draw mirrored video frame
  ctx.save();
  ctx.translate(W, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(results.image, 0, 0, W, H);
  ctx.restore();

  // FPS
  const fps = calcFps();
  lastFps = fps;
  fpsOverlay.textContent = `${fps} FPS`;
  mFps.textContent = fps;

  if (!results.multiFaceLandmarks || results.multiFaceLandmarks.length === 0) {
    mctx.clearRect(0, 0, mouthCanvas.width, mouthCanvas.height);
    mctx.fillStyle = '#0f172a';
    mctx.fillRect(0, 0, mouthCanvas.width, mouthCanvas.height);
    return;
  }

  const landmarks = results.multiFaceLandmarks[0];

  // Draw mirrored: flip canvas context around x-axis center
  ctx.save();
  ctx.translate(W, 0);
  ctx.scale(-1, 1);
  drawLipGroup(landmarks, OUTER_INDICES, '#22c55e', W, H);
  drawLipGroup(landmarks, INNER_INDICES, '#f97316', W, H);
  ctx.restore();

  // Side viewer
  drawMouthViewer(landmarks);

  // Metrics
  const { openness, width, ratio } = computeMetrics(landmarks);
  mOpenness.textContent = openness.toFixed(4);
  mWidth.textContent    = width.toFixed(4);
  mRatio.textContent    = ratio.toFixed(3);

  // Recording
  if (recording) {
    const t = (performance.now() - recordStart) / 1000;
    const pts = ALL_LIP_INDICES.map(i => ({
      x: landmarks[i].x,
      y: landmarks[i].y,
      z: landmarks[i].z ?? 0
    }));
    recordedFrames.push({ t: parseFloat(t.toFixed(4)), pts });
  }
}

// ── Camera & FaceMesh setup ───────────────────────────────────────────────────
async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false
    });
    video.srcObject = stream;
    await video.play();

    // Size canvas to match video
    video.addEventListener('loadedmetadata', () => {
      canvas.width  = video.videoWidth;
      canvas.height = video.videoHeight;
    }, { once: true });

    initFaceMesh();
    cameraRunning = true;
    btnCamera.textContent = 'カメラ停止';
    btnCamera.classList.remove('btn-primary');
    btnCamera.style.background = '#64748b';
    btnRecord.disabled = false;
    setStatus('running');
  } catch (e) {
    alert(`カメラの起動に失敗しました: ${e.message}`);
  }
}

function stopCamera() {
  if (video.srcObject) {
    video.srcObject.getTracks().forEach(t => t.stop());
    video.srcObject = null;
  }
  if (faceMesh) {
    faceMesh.close();
    faceMesh = null;
  }
  cameraRunning = false;
  recording = false;
  btnCamera.textContent = 'カメラ起動';
  btnCamera.classList.add('btn-primary');
  btnCamera.style.background = '';
  btnRecord.disabled = true;
  btnRecord.textContent = '録画開始';
  btnRecord.classList.remove('recording');
  setStatus('idle');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  mctx.clearRect(0, 0, mouthCanvas.width, mouthCanvas.height);
}

function initFaceMesh() {
  faceMesh = new FaceMesh({
    locateFile: (file) =>
      `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`
  });

  faceMesh.setOptions({
    maxNumFaces: 1,
    refineLandmarks: true,
    minDetectionConfidence: 0.5,
    minTrackingConfidence: 0.5
  });

  faceMesh.onResults(onResults);

  // Feed frames from video
  (async function sendFrames() {
    if (!faceMesh) return;
    if (!video.paused && video.readyState >= 2) {
      if (canvas.width === 0) {
        canvas.width  = video.videoWidth  || 640;
        canvas.height = video.videoHeight || 480;
      }
      await faceMesh.send({ image: video });
    }
    requestAnimationFrame(sendFrames);
  })();
}

// ── Recording controls ────────────────────────────────────────────────────────
function startRecording() {
  recordedFrames = [];
  recordStart = performance.now();
  recording = true;
  btnRecord.textContent = '録画停止';
  btnRecord.classList.add('recording');
  setStatus('rec');
}

function stopRecording() {
  recording = false;
  btnRecord.textContent = '録画開始';
  btnRecord.classList.remove('recording');
  setStatus('running');

  if (recordedFrames.length === 0) return;

  const duration = recordedFrames.at(-1).t;
  const fps = duration > 0 ? Math.round(recordedFrames.length / duration) : 0;
  const label = phraseInput.value.trim();
  const timestamp = new Date().toISOString();
  const filename = `lip_${label || 'unlabeled'}_${timestamp.replace(/[:.]/g, '-')}.json`;

  const output = {
    created: timestamp,
    label: label || null,
    outer_indices: OUTER_INDICES,
    inner_indices: INNER_INDICES,
    fps,
    frames: recordedFrames
  };

  downloadJSON(output, filename);
}

// ── Event listeners ───────────────────────────────────────────────────────────
btnCamera.addEventListener('click', () => {
  if (cameraRunning) stopCamera(); else startCamera();
});

btnRecord.addEventListener('click', () => {
  if (recording) stopRecording(); else startRecording();
});
