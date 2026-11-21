// Thin client for the FastAPI contract (DESIGN.md §5).
async function req(path, opts = {}) {
  const r = await fetch(`/api${path}`, opts)
  if (!r.ok) {
    let msg = r.statusText
    try { const j = await r.json(); msg = j.detail?.detail || JSON.stringify(j.detail) } catch {}
    throw new Error(msg)
  }
  return r.status === 204 ? null : r.json()
}

export const api = {
  upload: (form) => req('/sessions', { method: 'POST', body: form }),
  list: () => req('/sessions'),
  status: (id) => req(`/sessions/${id}`),
  analysis: (id) => req(`/sessions/${id}/analysis`),
  pose: (id) => req(`/sessions/${id}/pose`),
  remove: (id) => req(`/sessions/${id}`, { method: 'DELETE' }),
  setPhases: (id, phases) => req(`/sessions/${id}/phases`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phases }),
  }),
  videoUrl: (id) => `/api/sessions/${id}/video`,
  validation: () => req('/validation'),
  reprocess: (id) => req(`/sessions/${id}/reprocess`, { method: 'POST' }),
  setSettings: (id, body) => req(`/sessions/${id}/settings`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  setManualElbow: (id, body) => req(`/sessions/${id}/legality/manual`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  compare: (a, b) => req(`/compare?a=${a}&b=${b}`),
  trends: (metrics, bowler) => req(`/trends?metrics=${metrics}${bowler ? `&bowler_name=${encodeURIComponent(bowler)}` : ''}`),
  frameUrl: (id, f) => `/api/sessions/${id}/frames/${f}.jpg`,
  setCalibration: (id, body) => req(`/sessions/${id}/calibration`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  setManual: (id, body) => req(`/sessions/${id}/speed/manual`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
}

export const PHASES = ['run_up', 'gather', 'bfc', 'ffc', 'msr', 'br', 'follow_through']
export const PHASE_LABEL = {
  run_up: 'Run-up', gather: 'Gather', bfc: 'Back-Foot Contact', ffc: 'Front-Foot Contact',
  msr: 'Max Shoulder Rotation', br: 'Ball Release', follow_through: 'Follow-through',
}
export const STATUS_LABEL = {
  unavailable_low_confidence: 'Unavailable (Low Confidence)',
  unavailable_perspective: 'Unavailable (Camera View)',
  unavailable_not_detected: 'Unavailable (Not Detected)',
}
