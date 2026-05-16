// ── DTW (inlined – no ES module import needed) ───────────────────────────────
function frameDist(a, b) {
  let d = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    const dx = a[i].x - b[i].x;
    const dy = a[i].y - b[i].y;
    const dz = (a[i].z ?? 0) - (b[i].z ?? 0);
    d += dx * dx + dy * dy + dz * dz;
  }
  return d;
}

function dtw(seq1, seq2) {
  const n = seq1.length, m = seq2.length;
  if (n === 0 || m === 0) return Infinity;
  const dp = new Float64Array(n * m).fill(Infinity);
  dp[0] = frameDist(seq1[0], seq2[0]);
  for (let i = 1; i < n; i++) dp[i * m]     = dp[(i-1) * m]     + frameDist(seq1[i], seq2[0]);
  for (let j = 1; j < m; j++) dp[j]         = dp[j-1]           + frameDist(seq1[0], seq2[j]);
  for (let i = 1; i < n; i++) {
    for (let j = 1; j < m; j++) {
      dp[i*m+j] = frameDist(seq1[i], seq2[j]) +
        Math.min(dp[(i-1)*m+j], dp[i*m+(j-1)], dp[(i-1)*m+(j-1)]);
    }
  }
  return dp[n*m-1] / (n + m);
}

// ── Landmark indices ──────────────────────────────────────────────────────────
const OUTER_INDICES = [0,267,269,270,409,291,375,321,405,314,17,84,181,91,146,61,185,40,39,37];
const INNER_INDICES = [78,95,88,178,87,14,317,402,318,324,308,415,310,311,312,13,82,81,80,191];
const ALL_LIP_INDICES = [...OUTER_INDICES, ...INNER_INDICES];

const RECOG_FRAMES = 60; // frames to collect before each DTW run

// ── DOM refs ─────────────────────────────────────────────────────────────────
const video              = document.getElementById('video');
const canvas             = document.getElementById('canvas');
const ctx                = canvas.getContext('2d');
const mouthCanvas        = document.getElementById('mouth-canvas');
const mctx               = mouthCanvas.getContext('2d');
const statusBadge        = document.getElementById('status-badge');
const fpsOverlay         = document.getElementById('fps-overlay');
const btnCamera          = document.getElementById('btn-camera');
const btnRecord          = document.getElementById('btn-record');
const btnRecog           = document.getElementById('btn-recog');
const phraseInput        = document.getElementById('phrase-label');
const mOpenness          = document.getElementById('m-openness');
const mWidth             = document.getElementById('m-width');
const mRatio             = document.getElementById('m-ratio');
const mFps               = document.getElementById('m-fps');
const dropZone           = document.getElementById('drop-zone');
const fileInput          = document.getElementById('file-input');
const templateList       = document.getElementById('template-list');
const recogStatusMsg     = document.getElementById('recog-status');
const resultList         = document.getElementById('result-list');
const feedbackSection    = document.getElementById('feedback-section');
const feedbackSelect     = document.getElementById('feedback-select');
const btnFeedbackOk      = document.getElementById('btn-feedback-ok');
const recogProgressEl    = document.getElementById('recog-progress');
const recogProgressBar   = document.getElementById('recog-progress-bar');
const recogProgressLabel = document.getElementById('recog-progress-label');

// ── State ─────────────────────────────────────────────────────────────────────
let faceMesh = null;
let cameraRunning = false;
let recording = false;
let recordedFrames = [];
let recordStart = 0;

// Template store: label -> [{frames, created}]
const templateStore = new Map();

// Recognition
let recognizing = false;
let recogBuffer = [];
let recogStart = 0;
let lastRecogFrames = null;
let dtwRunning = false;

// FPS tracking
let frameTimes = [];

// ── Utility ───────────────────────────────────────────────────────────────────
function setStatus(mode) {
  statusBadge.className = `badge badge-${mode}`;
  const labels = { idle: '待機中', running: '検出中', rec: '録画中', recog: '認識中' };
  statusBadge.textContent = labels[mode] ?? mode;
}

function calcFps() {
  const now = performance.now();
  frameTimes.push(now);
  frameTimes = frameTimes.filter(t => t > now - 1000);
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

// ── Tab system ────────────────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === name);
  });
  document.querySelectorAll('.tab-content').forEach(pane => {
    pane.classList.toggle('active', pane.id === `tab-${name}`);
  });
}

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ── Drawing helpers ───────────────────────────────────────────────────────────
function drawLipGroup(landmarks, indices, color, scaleX, scaleY) {
  ctx.fillStyle = color;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.font = 'bold 9px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  ctx.beginPath();
  indices.forEach((idx, i) => {
    const lm = landmarks[idx];
    const x = lm.x * scaleX;
    const y = lm.y * scaleY;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.globalAlpha = 0.55;
  ctx.stroke();
  ctx.globalAlpha = 1;

  indices.forEach(idx => {
    const lm = landmarks[idx];
    const x = lm.x * scaleX;
    const y = lm.y * scaleY;
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.fillRect(x - 7, y - 17, 14, 11);
    ctx.fillStyle = color;
    ctx.fillText(String(idx), x, y - 11);
  });
}

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

  const norm = p => ({
    x: W - pad - ((p.x - minX) / rangeX) * (W - pad * 2),
    y: pad + ((p.y - minY) / rangeY) * (H - pad * 2)
  });

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

function computeMetrics(landmarks) {
  const top    = landmarks[13];
  const bottom = landmarks[14];
  const left   = landmarks[61];
  const right  = landmarks[291];
  const height = Math.hypot(top.x - bottom.x, top.y - bottom.y);
  const width  = Math.hypot(left.x - right.x, left.y - right.y);
  return { openness: height, width, ratio: width > 0 ? height / width : 0 };
}

// ── FaceMesh callback ─────────────────────────────────────────────────────────
function onResults(results) {
  const W = canvas.width;
  const H = canvas.height;

  ctx.save();
  ctx.translate(W, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(results.image, 0, 0, W, H);
  ctx.restore();

  const fps = calcFps();
  fpsOverlay.textContent = `${fps} FPS`;
  mFps.textContent = fps;

  if (!results.multiFaceLandmarks?.length) {
    mctx.fillStyle = '#0f172a';
    mctx.fillRect(0, 0, mouthCanvas.width, mouthCanvas.height);
    return;
  }

  const landmarks = results.multiFaceLandmarks[0];

  ctx.save();
  ctx.translate(W, 0);
  ctx.scale(-1, 1);
  drawLipGroup(landmarks, OUTER_INDICES, '#22c55e', W, H);
  drawLipGroup(landmarks, INNER_INDICES, '#f97316', W, H);
  ctx.restore();

  drawMouthViewer(landmarks);

  const { openness, width, ratio } = computeMetrics(landmarks);
  mOpenness.textContent = openness.toFixed(4);
  mWidth.textContent    = width.toFixed(4);
  mRatio.textContent    = ratio.toFixed(3);

  // Current frame points (shared by recording and recognition)
  const pts = ALL_LIP_INDICES.map(i => ({
    x: landmarks[i].x,
    y: landmarks[i].y,
    z: landmarks[i].z ?? 0
  }));

  if (recording) {
    const t = parseFloat(((performance.now() - recordStart) / 1000).toFixed(4));
    recordedFrames.push({ t, pts });
  }

  if (recognizing) {
    const t = parseFloat(((performance.now() - recogStart) / 1000).toFixed(4));
    recogBuffer.push({ t, pts });
    updateRecogProgress();

    if (recogBuffer.length >= RECOG_FRAMES && !dtwRunning) {
      dtwRunning = true;
      const frames = [...recogBuffer];
      recogBuffer = [];
      updateRecogProgress();
      // Run off the animation frame to avoid blocking rendering
      setTimeout(() => {
        runRecognition(frames).finally(() => { dtwRunning = false; });
      }, 0);
    }
  }
}

// ── Camera & FaceMesh setup ───────────────────────────────────────────────────
async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    alert('このブラウザはカメラAPIに対応していません。Chrome/Firefox/Safari の最新版をお使いください。');
    return;
  }
  if (typeof FaceMesh === 'undefined') {
    alert('MediaPipe の読み込みに失敗しました。インターネット接続を確認して再読み込みしてください。');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false
    });
    video.srcObject = stream;

    await new Promise((resolve, reject) => {
      video.addEventListener('loadedmetadata', resolve, { once: true });
      video.addEventListener('error', reject, { once: true });
    });

    canvas.width  = video.videoWidth  || 640;
    canvas.height = video.videoHeight || 480;

    await video.play();
    initFaceMesh();

    cameraRunning = true;
    btnCamera.textContent = 'カメラ停止';
    btnCamera.classList.remove('btn-primary');
    btnCamera.style.background = '#64748b';
    btnRecord.disabled = false;
    setStatus('running');
    updateRecogUI();
  } catch (e) {
    const msg = e.name === 'NotAllowedError'
      ? 'カメラのアクセス許可が拒否されました。ブラウザの設定でカメラを許可してください。'
      : e.name === 'NotFoundError'
        ? 'カメラが見つかりません。カメラが接続されているか確認してください。'
        : `カメラの起動に失敗しました: ${e.message}`;
    alert(msg);
  }
}

function stopCamera() {
  if (recognizing) stopRecognition();

  if (video.srcObject) {
    video.srcObject.getTracks().forEach(t => t.stop());
    video.srcObject = null;
  }
  if (faceMesh) { faceMesh.close(); faceMesh = null; }

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
  updateRecogUI();
}

function initFaceMesh() {
  faceMesh = new FaceMesh({
    locateFile: file => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`
  });
  faceMesh.setOptions({
    maxNumFaces: 1,
    refineLandmarks: true,
    minDetectionConfidence: 0.5,
    minTrackingConfidence: 0.5
  });
  faceMesh.onResults(onResults);

  (async function sendFrames() {
    if (!faceMesh) return;
    if (!video.paused && video.readyState >= 2) {
      try { await faceMesh.send({ image: video }); }
      catch (e) { console.warn('FaceMesh send error:', e); }
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
  btnRecog.disabled = true;
  setStatus('rec');
}

function stopRecording() {
  recording = false;
  btnRecord.textContent = '録画開始';
  btnRecord.classList.remove('recording');
  setStatus('running');
  updateRecogUI();

  if (recordedFrames.length === 0) return;

  const duration = recordedFrames.at(-1).t;
  const fps = duration > 0 ? Math.round(recordedFrames.length / duration) : 0;
  const label = phraseInput.value.trim();
  const timestamp = new Date().toISOString();
  const filename = `lip_${label || 'unlabeled'}_${timestamp.replace(/[:.]/g, '-')}.json`;

  downloadJSON({
    created: timestamp,
    label: label || null,
    outer_indices: OUTER_INDICES,
    inner_indices: INNER_INDICES,
    fps,
    frames: recordedFrames
  }, filename);
}

// ── Template management ───────────────────────────────────────────────────────
async function loadTemplateFiles(files) {
  let added = 0;
  for (const file of files) {
    try {
      const json = JSON.parse(await file.text());
      if (!Array.isArray(json.frames) || json.frames.length === 0) continue;
      const label = (json.label || file.name.replace(/\.json$/i, '')).trim();
      if (!templateStore.has(label)) templateStore.set(label, []);
      templateStore.get(label).push({ frames: json.frames, created: json.created ?? new Date().toISOString() });
      added++;
    } catch (e) {
      console.warn('Template load error:', file.name, e);
    }
  }
  if (added > 0) {
    renderTemplateList();
    updateRecogUI();
  }
  return added;
}

function renderTemplateList() {
  if (templateStore.size === 0) {
    templateList.innerHTML = '<p class="empty-hint">JSONファイルをドロップして読み込んでください</p>';
    return;
  }
  templateList.innerHTML = '';
  for (const [label, recs] of templateStore) {
    const avgF = Math.round(recs.reduce((s, r) => s + r.frames.length, 0) / recs.length);
    const group = document.createElement('div');
    group.className = 'tpl-group';
    group.innerHTML = `
      <div class="tpl-header">
        <span class="tpl-label-badge">${escHtml(label)}</span>
        <span class="tpl-meta">${recs.length}件・平均 ${avgF}f</span>
      </div>
      <div class="tpl-items">
        ${recs.map((r, i) => `
          <div class="tpl-item">
            <span>録画${i + 1}（${r.frames.length} f）</span>
            <button class="btn-del" data-label="${escAttr(label)}" data-idx="${i}" title="削除">✕</button>
          </div>
        `).join('')}
      </div>`;
    templateList.appendChild(group);
  }

  templateList.querySelectorAll('.btn-del').forEach(btn => {
    btn.addEventListener('click', () => {
      const label = btn.dataset.label;
      const idx   = Number(btn.dataset.idx);
      const recs  = templateStore.get(label);
      if (!recs) return;
      recs.splice(idx, 1);
      if (recs.length === 0) templateStore.delete(label);
      renderTemplateList();
      updateRecogUI();
    });
  });
}

function escHtml(s)  { return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function escAttr(s)  { return s.replace(/"/g, '&quot;'); }

// ── Recognition mode ──────────────────────────────────────────────────────────
function updateRecogUI() {
  const hasTemplates = templateStore.size > 0;
  btnRecog.disabled = !cameraRunning || !hasTemplates || recording;

  if (hasTemplates) {
    recogStatusMsg.textContent = `${templateStore.size} フレーズ読み込み済み。認識モードを開始できます。`;
  } else {
    recogStatusMsg.textContent = 'テンプレートを読み込んでから認識モードを開始してください';
  }
}

function startRecognition() {
  recognizing = true;
  recogBuffer = [];
  recogStart  = performance.now();
  dtwRunning  = false;

  btnRecog.textContent = '認識停止';
  btnRecog.classList.add('btn-recog-active');
  btnRecord.disabled = true;
  recogProgressEl.classList.remove('hidden');
  updateRecogProgress();
  setStatus('recog');
  switchTab('results');

  resultList.innerHTML = '<div class="recog-waiting">口パクを検出中…</div>';
  feedbackSection.classList.add('hidden');
}

function stopRecognition() {
  recognizing = false;
  recogBuffer = [];
  dtwRunning  = false;

  btnRecog.textContent = '認識モード';
  btnRecog.classList.remove('btn-recog-active');
  btnRecord.disabled = false;
  recogProgressEl.classList.add('hidden');
  setStatus('running');
}

function updateRecogProgress() {
  const pct = Math.min(100, Math.round(recogBuffer.length / RECOG_FRAMES * 100));
  recogProgressBar.style.width = `${pct}%`;
  recogProgressLabel.textContent = dtwRunning ? '照合中…' : `収集中… ${recogBuffer.length}/${RECOG_FRAMES}`;
}

async function runRecognition(frames) {
  if (templateStore.size === 0) return;

  const querySeq = frames.map(f => f.pts);
  const candidates = [];

  for (const [label, recs] of templateStore) {
    let best = Infinity;
    for (const rec of recs) {
      const d = dtw(querySeq, rec.frames.map(f => f.pts));
      if (d < best) best = d;
    }
    candidates.push({ label, dist: best });
  }

  candidates.sort((a, b) => a.dist - b.dist);

  // Inverse-distance weighting → confidence %
  const invScores = candidates.map(c => 1 / (1e-9 + c.dist));
  const total = invScores.reduce((a, b) => a + b, 0);
  const top3 = candidates.slice(0, 3).map((c, i) => ({
    label: c.label,
    dist:  c.dist,
    pct:   Math.round(invScores[i] / total * 100)
  }));

  renderResults(top3, frames);
  speak(top3[0].label);
}

function renderResults(results, frames) {
  lastRecogFrames = frames;

  const rankColors = ['#22c55e', '#f97316', '#94a3b8'];
  resultList.innerHTML = results.map((r, i) => `
    <div class="result-card ${i === 0 ? 'result-top' : ''}">
      <div class="result-rank" style="background:${rankColors[i]}">${i + 1}位</div>
      <div class="result-body">
        <div class="result-label">${escHtml(r.label)}</div>
        <div class="conf-bar-wrap">
          <div class="conf-bar" style="width:${r.pct}%;background:${rankColors[i]}"></div>
        </div>
      </div>
      <div class="conf-pct">${r.pct}%</div>
    </div>
  `).join('');

  // Populate feedback select
  feedbackSelect.innerHTML = [...templateStore.keys()]
    .map(lbl => `<option value="${escAttr(lbl)}">${escHtml(lbl)}</option>`)
    .join('');
  // Pre-select the first result as wrong guess → suggest correct
  feedbackSection.classList.remove('hidden');
}

function speak(text) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  utt.lang = 'ja-JP';
  utt.rate = 0.9;
  window.speechSynthesis.speak(utt);
}

function addFeedback(correctLabel) {
  if (!lastRecogFrames || !templateStore.has(correctLabel)) return;

  templateStore.get(correctLabel).push({
    frames:  lastRecogFrames,
    created: new Date().toISOString()
  });
  renderTemplateList();

  // Download the new recording as a standalone JSON
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  downloadJSON({
    created: new Date().toISOString(),
    label: correctLabel,
    outer_indices: OUTER_INDICES,
    inner_indices: INNER_INDICES,
    fps: Math.round(lastRecogFrames.length / (lastRecogFrames.at(-1).t || 1)),
    frames: lastRecogFrames
  }, `lip_${correctLabel}_feedback_${ts}.json`);

  feedbackSection.classList.add('hidden');
  const ok = document.createElement('div');
  ok.className = 'feedback-ok';
  ok.textContent = `「${correctLabel}」に追加しました ✓`;
  resultList.appendChild(ok);
  setTimeout(() => ok.remove(), 2500);
  lastRecogFrames = null;
}

// ── Drop zone ─────────────────────────────────────────────────────────────────
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', async e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const files = [...e.dataTransfer.files].filter(f => f.name.endsWith('.json'));
  if (files.length) {
    const n = await loadTemplateFiles(files);
    if (n) switchTab('templates');
  }
});

fileInput.addEventListener('change', async () => {
  if (fileInput.files.length) {
    const n = await loadTemplateFiles([...fileInput.files]);
    if (n) switchTab('templates');
    fileInput.value = '';
  }
});

// ── Button event listeners ────────────────────────────────────────────────────
btnCamera.addEventListener('click', () => {
  if (cameraRunning) stopCamera(); else startCamera();
});

btnRecord.addEventListener('click', () => {
  if (recording) stopRecording(); else startRecording();
});

btnRecog.addEventListener('click', () => {
  if (recognizing) stopRecognition(); else startRecognition();
});

btnFeedbackOk.addEventListener('click', () => {
  addFeedback(feedbackSelect.value);
});
