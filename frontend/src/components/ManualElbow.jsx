import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Card } from './ui'

const VIEW = 360                                   // canvas size (px)
const STEPS = ['Shoulder', 'Elbow', 'Wrist']
const COLORS = ['#f472b6', '#facc15', '#38bdf8']

const angleOf = (S, E, W) => {
  const a = [S[0] - E[0], S[1] - E[1]], b = [W[0] - E[0], W[1] - E[1]]
  const c = (a[0] * b[0] + a[1] * b[1]) / (Math.hypot(...a) * Math.hypot(...b))
  return (Math.acos(Math.max(-1, Math.min(1, c))) * 180) / Math.PI
}

/** Zoomed digitising tool: click shoulder → elbow → wrist on key frames (arm horizontal → release). */
export default function ManualElbow({ id, report, onReport }) {
  const L = report.legality
  const armIds = report.bowling_arm === 'right' ? [12, 14, 16] : [11, 13, 15]
  const total = report.meta.total_frames
  const [pose, setPose] = useState(null)
  const [frame, setFrame] = useState(L.manual?.inputs?.[0]?.frame ?? L.suggested_frames[0] ?? 0)
  const [saved, setSaved] = useState(() => Object.fromEntries((L.manual?.inputs || []).map((p) => [p.frame, [p.shoulder, p.elbow, p.wrist]])))
  const [cur, setCur] = useState([])
  const [zoom, setZoom] = useState(1)
  const [img, setImg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const cvs = useRef(null)
  // frames the AUTOMATIC result is calculated from (Δ = release − most bent); not shown once a manual result exists
  const calcFrames = L.manual ? {} : Object.fromEntries(
    [[L.min_frame, 'most bent'], [L.br_used, 'release']].filter(([f]) => f != null))

  useEffect(() => { api.pose(id).then(setPose) }, [id])
  useEffect(() => {
    const im = new Image(); im.onload = () => setImg(im); im.src = api.frameUrl(id, frame)
    setCur(saved[frame] ? [...saved[frame]] : [])
  }, [id, frame]) // eslint-disable-line

  // crop: covers the WHOLE bowling arm (shoulder, elbow, wrist + hand) with margin, so a fast-moving hand
  // never leaves the view. Uses this frame's points, else the nearest tracked frames on both sides (union),
  // and never smaller than ~1 arm length around the shoulder (arm can rotate anywhere around it).
  const crop = (() => {
    const W = report.meta.width, H = report.meta.height
    let c = [W / 2, H / 2], side = Math.min(W, H) / 2
    if (pose) {
      const armPts = [], body = []
      for (let d = 0; d < 15 && armPts.length < 6; d++) {
        for (const f of d ? [frame - d, frame + d] : [frame]) {
          const lm = pose.frames[f]?.lm
          if (!lm) continue
          ;[...armIds, armIds[2] + 4].forEach((i) => { const p = lm[i]; if (p && p[0] >= 0 && p[2] >= 0.2) armPts.push([p[0], p[1]]) })
          if (!body.length) lm.forEach((p) => { if (p[0] >= 0 && p[2] >= 0.3) body.push(p[1]) })
        }
      }
      if (armPts.length >= 2) {
        // the hand can be anywhere on a circle around the shoulder -> centre on the shoulder, half-size = arm reach
        const sh = armPts[0]
        const reach = Math.max(...armPts.map((p) => Math.hypot(p[0] - sh[0], p[1] - sh[1])), 40) * 1.15
        const bodyH = body.length ? Math.max(...body) - Math.min(...body) : 0
        side = Math.max(reach * 2.6, bodyH * 0.6, 120)
        c = sh
      }
    }
    side /= zoom
    return { x: c[0] - side / 2, y: c[1] - side / 2, s: side }
  })()
  const toView = (p) => [((p[0] - crop.x) / crop.s) * VIEW, ((p[1] - crop.y) / crop.s) * VIEW]

  useEffect(() => {
    const ctx = cvs.current?.getContext('2d')
    if (!ctx || !img) return
    ctx.fillStyle = '#0f172a'; ctx.fillRect(0, 0, VIEW, VIEW)
    ctx.drawImage(img, crop.x, crop.y, crop.s, crop.s, 0, 0, VIEW, VIEW)
    // automatic points ONLY on the frames the automatic legality calculation uses
    const used = calcFrames[frame]
    const lm = pose?.frames[frame]?.lm
    if (used && lm && armIds.every((i) => lm[i][0] >= 0)) {
      const a = armIds.map((i) => toView(lm[i]))
      ctx.strokeStyle = '#0f172a'; ctx.lineWidth = 5
      ctx.beginPath(); ctx.moveTo(...a[0]); ctx.lineTo(...a[1]); ctx.lineTo(...a[2]); ctx.stroke()
      ctx.strokeStyle = '#fbbf24'; ctx.lineWidth = 2.5
      ctx.beginPath(); ctx.moveTo(...a[0]); ctx.lineTo(...a[1]); ctx.lineTo(...a[2]); ctx.stroke()
      a.forEach(([x, y], i) => {
        ctx.fillStyle = '#0f172a'; ctx.beginPath(); ctx.arc(x, y, 7, 0, 7); ctx.fill()
        ctx.fillStyle = COLORS[i]; ctx.beginPath(); ctx.arc(x, y, 5, 0, 7); ctx.fill()
      })
      const ang = L.timeline[frame]?.angle
      ctx.fillStyle = 'rgba(2,6,23,0.85)'; ctx.fillRect(6, 6, VIEW - 12, 24)
      ctx.fillStyle = '#fde68a'; ctx.font = 'bold 13px Inter, sans-serif'
      ctx.fillText(`Used in calculation · ${used} · elbow ${ang != null ? ang.toFixed(1) + '°' : '—'}`, 12, 23)
    }
    const v = cur.map(toView)
    ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 2
    if (v.length > 1) { ctx.beginPath(); ctx.moveTo(...v[0]); v.slice(1).forEach((p) => ctx.lineTo(...p)); ctx.stroke() }
    v.forEach(([x, y], i) => { ctx.fillStyle = COLORS[i]; ctx.beginPath(); ctx.arc(x, y, 5, 0, 7); ctx.fill() })
  }) // redraw every render (cheap)

  const click = (e) => {
    if (cur.length >= 3) return
    const r = e.currentTarget.getBoundingClientRect()
    const vx = ((e.clientX - r.left) / r.width) * VIEW, vy = ((e.clientY - r.top) / r.height) * VIEW
    setCur([...cur, [crop.x + (vx / VIEW) * crop.s, crop.y + (vy / VIEW) * crop.s]])
  }
  const saveFrame = () => { setSaved({ ...saved, [frame]: cur }) }
  const removeFrame = (f) => { const s = { ...saved }; delete s[f]; setSaved(s) }
  const submit = async (clear = false) => {
    setBusy(true); setErr('')
    try {
      const points = Object.entries(saved).map(([f, [S, E, W]]) => ({ frame: +f, shoulder: S, elbow: E, wrist: W }))
      onReport(await api.setManualElbow(id, clear ? null : { points }))
      if (clear) setSaved({})
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  const btn = 'rounded bg-slate-800 px-2 py-1 text-sm hover:bg-slate-700 disabled:opacity-40'
  const frames = Object.keys(saved).map(Number).sort((a, b) => a - b)

  return (
    <Card title="Manual elbow verification (digitise key frames)">
      <p className="mb-2 text-xs text-slate-400">
        Digitise the bowling arm on the <b>arm-horizontal</b> frame, the <b>release</b> frame and 1–2 frames between.
        Click <span style={{ color: COLORS[0] }}>shoulder</span> → <span style={{ color: COLORS[1] }}>elbow</span> → <span style={{ color: COLORS[2] }}>wrist</span> (centre of each joint).
      </p>
      <div className="flex flex-wrap gap-4">
        <div>
          <canvas ref={cvs} width={VIEW} height={VIEW} onClick={click} className="max-w-full cursor-crosshair rounded border border-slate-700" />
          <div className="mt-1 flex flex-wrap items-center gap-1 text-sm">
            <button className={btn} onClick={() => setFrame(Math.max(0, frame - 1))}>◀</button>
            <span className="font-mono">frame {frame}</span>
            <button className={btn} onClick={() => setFrame(Math.min(total - 1, frame + 1))}>▶</button>
            <button className={btn} onClick={() => setZoom(Math.max(0.5, zoom / 1.4))}>−</button>
            <button className={btn} onClick={() => setZoom(Math.min(6, zoom * 1.4))}>+ zoom</button>
          </div>
        </div>
        <div className="min-w-56 flex-1 space-y-2 text-sm">
          {Object.keys(calcFrames).length > 0 && (
            <div>Calculation frames: {Object.entries(calcFrames).map(([f, label]) => (
              <button key={f} className={`mr-1 rounded px-2 py-1 text-sm ${+f === frame ? 'bg-amber-500 text-slate-950' : 'bg-amber-500/15 text-amber-200 hover:bg-amber-500/25'}`}
                      onClick={() => setFrame(+f)}>{f} ({label})</button>
            ))}</div>
          )}
          <div>Suggested: {L.suggested_frames.map((f) => (
            <button key={f} className={`mr-1 rounded px-2 py-1 text-sm ${f === frame ? 'bg-emerald-600 text-white' : 'bg-slate-800 hover:bg-slate-700'}`} onClick={() => setFrame(f)}>{f}{f === L.horizontal_frame ? ' (arm horiz.)' : f === L.br_frame ? ' (release)' : ''}</button>
          ))}</div>
          <div>Next click: <b>{cur.length < 3 ? STEPS[cur.length] : 'done'}</b>
            {cur.length === 3 && <span className="ml-2 font-mono text-emerald-300">elbow {angleOf(...cur).toFixed(1)}°</span>}</div>
          <div className="flex flex-wrap gap-1">
            <button className={btn} disabled={cur.length !== 3} onClick={saveFrame}>Save frame {frame}</button>
            <button className={btn} onClick={() => setCur([])}>Reset clicks</button>
          </div>
          <div className="border-t border-slate-800 pt-2">
            <div className="text-xs text-slate-500">Digitised frames (first = arm horizontal, last = release):</div>
            {frames.length === 0 && <i className="text-slate-500">none yet</i>}
            {frames.map((f) => (
              <div key={f} className="flex items-center justify-between font-mono">
                <button className="underline" onClick={() => setFrame(f)}>#{f}</button>
                <span>{angleOf(...saved[f]).toFixed(1)}°</span>
                <button className="text-rose-400" onClick={() => removeFrame(f)}>✕</button>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-1">
            <button className="rounded bg-emerald-700 px-3 py-1 disabled:opacity-40" disabled={frames.length < 2 || busy} onClick={() => submit(false)}>{busy ? 'Computing…' : 'Compute verified result'}</button>
            {L.manual && <button className={btn} disabled={busy} onClick={() => submit(true)}>Clear manual result</button>}
          </div>
          {err && <p className="text-rose-400">{err}</p>}
        </div>
      </div>
    </Card>
  )
}
