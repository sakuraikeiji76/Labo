/**
 * Frame-level distance: squared Euclidean sum across all lip landmarks.
 * Squared distance avoids sqrt for a significant speed-up; ranking is preserved.
 * @param {Array<{x,y,z}>} a
 * @param {Array<{x,y,z}>} b
 * @returns {number}
 */
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

/**
 * DTW distance between two lip-landmark sequences.
 * Normalised by path length so longer/shorter recordings are comparable.
 *
 * @param {Array<Array<{x,y,z}>>} seq1  frames × 40 points
 * @param {Array<Array<{x,y,z}>>} seq2  frames × 40 points
 * @returns {number} Normalised DTW cost (lower = more similar)
 */
export function dtw(seq1, seq2) {
  const n = seq1.length;
  const m = seq2.length;
  if (n === 0 || m === 0) return Infinity;

  // Flat Float64 matrix, row-major
  const dp = new Float64Array(n * m).fill(Infinity);

  dp[0] = frameDist(seq1[0], seq2[0]);
  for (let i = 1; i < n; i++) dp[i * m]     = dp[(i - 1) * m]     + frameDist(seq1[i], seq2[0]);
  for (let j = 1; j < m; j++) dp[j]         = dp[j - 1]           + frameDist(seq1[0], seq2[j]);

  for (let i = 1; i < n; i++) {
    for (let j = 1; j < m; j++) {
      const prev = Math.min(
        dp[(i - 1) * m + j],
        dp[i * m + (j - 1)],
        dp[(i - 1) * m + (j - 1)]
      );
      dp[i * m + j] = frameDist(seq1[i], seq2[j]) + prev;
    }
  }

  return dp[n * m - 1] / (n + m);
}
