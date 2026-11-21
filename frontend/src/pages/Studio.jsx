import { useCallback, useEffect, useRef, useState } from 'react'
import { api, PHASES, PHASE_LABEL } from '../api'
import { Card } from '../components/ui'
import VirtualSkeleton from '../components/VirtualSkeleton'

const SIDE = {
  right: { arm: [12, 14, 16], leg: [23, 25, 27] },   // bowling arm S-E-W, front leg H-K-A (left leg)
  left: { arm: [11, 13, 15], leg: [24, 26, 28] },
}
const SHORT = { run_up: 'RUN', gather: 'GAT', bfc: 'BFC', ffc: 'FFC', msr: 'MSR', br: 'BR', follow_through: 'FT' }
const visColor =(v) => (v >= 0.7 ? '#34d399' : v >= 0.5 ? '#fbbf24' : '#f43f5e')

function drawArc(ctx, A, B, C, label, s) {
  const a1 = Math.atan2(A[1] - B[1], A[0] - B[0]), a2 = Math.atan2(C[1] - B[1], C[0] - B[0])
  let d = a2 - a1
  while (d > Math.PI) d -= 2 * Math.PI
  while (d < -Math.PI) d += 2 * Math.PI
  ctx.strokeStyle = '#38bdf8'; ctx.lineWidth = 2
  ctx.beginPath(); ctx.arc(B[0] * s, B[1] * s, 24, a1, a1 + d, d < 0); ctx.stroke()
  ctx.fillStyle = '#0c4a6e'; ctx.fillRect(B[0] * s + 10, B[1] * s - 28, 46, 18)
  ctx.fillStyle = '#e0f2fe'; ctx.font = '12px monospace'; ctx.fillText(label, B[0] * s + 13, B[1] * s - 15)
}

export default function Studio({ id, report, onReport }) {
  const vid = useRef(null), cvs = useRef(null)
  const [pose, setPose] = useState(null)
  const [frame, setFrame] = useState(0)
  const [rate, setRate] = useState(1)
  const [showSkel, setShowSkel] = useState(true)
  const [showArcs, setShowArcs] = useState(true)
  const [editPhase, setEditPhase] = useState('ffc')
  const [busy, setBusy] = useState(false)
  const [muted, setMuted] = useState(true)       // audio off by default (classroom demo)
  const fps = report.meta.fps, total = report.meta.total_frames

  useEffect(() => { api.pose(id).then(setPose) }, [id])

  const draw = useCallback((f) => {
    const c = cvs.current, v = vid.current
    if (!c || !v || !pose) return
    c.width = v.clientWidth; c.height = v.clientHeight
    const ctx = c.getContext('2d'); ctx.clearRect(0, 0, c.width, c.height)
    const s = c.width / pose.meta.width
    // ball detections up to the current frame
    const bt = report.speed?.track || []
    ctx.fillStyle = '#facc15'
    for (const [bf, bx, by] of bt) {
      if (bf > f) break
      ctx.beginPath(); ctx.arc(bx * s, by * s, bf === f ? 6 : 3, 0, 7); ctx.fill()
    }
    const fr = pose.frames[Math.min(f, pose.frames.length - 1)]
    if (!fr?.lm) return
    const L = fr.lm
    if (showSkel) {
      ctx.lineWidth = 3
      for (const [a, b] of pose.connections) {
        const v1 = Math.min(L[a][2], L[b][2])
        if (L[a][0] < 0 || L[b][0] < 0 || v1 < 0.5) continue
        ctx.strokeStyle = visColor(v1)
        ctx.beginPath(); ctx.moveTo(L[a][0] * s, L[a][1] * s); ctx.lineTo(L[b][0] * s, L[b][1] * s); ctx.stroke()
      }
      for (const p of L) {
        if (p[0] < 0) continue
        ctx.fillStyle = visColor(p[2]); ctx.beginPath(); ctx.arc(p[0] * s, p[1] * s, 3.5, 0, 7); ctx.fill()
      }
    }
    if (showArcs) {
      const sd = SIDE[report.bowling_arm]
      const ok = (ids) => ids.every((i) => L[i][0] >= 0 && L[i][2] >= 0.5)
      if (ok(sd.arm) && fr.angles.elbow_bowl != null) drawArc(ctx, L[sd.arm[0]], L[sd.arm[1]], L[sd.arm[2]], `${fr.angles.elbow_bowl.toFixed(0)}°`, s)
      if (ok(sd.leg) && fr.angles.knee_front != null) drawArc(ctx, L[sd.leg[0]], L[sd.leg[1]], L[sd.leg[2]], `${fr.angles.knee_front.toFixed(0)}°`, s)
    }
  }, [pose, showSkel, showArcs, report.bowling_arm, report.speed])

  // sync canvas to the exact decoded frame
  useEffect(() => {
    const v = vid.current
    if (!v) return
    let handle
    const tick = (_, meta) => {
      const f = Math.round(meta.mediaTime * fps)
      setFrame(f); draw(f)
      handle = v.requestVideoFrameCallback(tick)
    }
    if (v.requestVideoFrameCallback) handle = v.requestVideoFrameCallback(tick)
    const onSeek = () => { const f = Math.floor(v.currentTime * fps + 1e-6); setFrame(f); draw(f) }
    v.addEventListener('seeked', onSeek); v.addEventListener('timeupdate', onSeek)
    return () => { v.cancelVideoFrameCallback?.(handle); v.removeEventListener('seeked', onSeek); v.removeEventListener('timeupdate', onSeek) }
  }, [draw, fps])

  useEffect(() => { draw(frame) }, [draw]) // eslint-disable-line
  useEffect(() => { if (vid.current) vid.current.playbackRate = rate }, [rate])

  const seek = (f) => { const v = vid.current; v.pause(); v.currentTime = (Math.max(0, Math.min(f, total - 1)) + 0.5) / fps }
  const savePhase = async (val) => {
    setBusy(true)
    try { onReport(await api.setPhases(id, { [editPhase]: val })) } finally { setBusy(false) }
  }
  const ang = pose?.frames[frame]?.angles || {}
  const btn = 'rounded bg-slate-800 px-3 py-1 text-sm hover:bg-slate-700'

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
      <Card>
        {/* w-fit wrapper: canvas matches the video's displayed box; height capped so portrait clips stay small */}
        <div className="relative mx-auto w-fit">
          <video ref={vid} src={api.videoUrl(id)} className="block max-h-[65vh] w-auto max-w-full rounded" controls={false} playsInline preload="auto" muted={muted} />
          <canvas ref={cvs} className="pointer-events-none absolute left-0 top-0" />
          {!pose && <div className="absolute inset-0 grid place-items-center text-slate-400">Loading pose data…</div>}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className={btn} onClick={() => (vid.current.paused ? vid.current.play() : vid.current.pause())}>Play / Pause</button>
          <button className={btn} onClick={() => seek(frame - 1)}>◀ Frame</button>
          <button className={btn} onClick={() => seek(frame + 1)}>Frame ▶</button>
          {[0.25, 0.5, 1].map((r) => (
            <button key={r} aria-pressed={rate === r}
                    className={`rounded px-3 py-1 text-sm font-medium ${rate === r ? 'bg-emerald-500 text-slate-950 ring-2 ring-emerald-300/40' : 'bg-slate-800 hover:bg-slate-700'}`}
                    onClick={() => setRate(r)}>{r}x</button>
          ))}
          <button className={btn} onClick={() => setMuted((m) => !m)}>{muted ? '🔇 Sound off' : '🔊 Sound on'}</button>
          <label className="ml-2 text-sm"><input type="checkbox" checked={showSkel} onChange={(e) => setShowSkel(e.target.checked)} /> Skeleton</label>
          <label className="text-sm"><input type="checkbox" checked={showArcs} onChange={(e) => setShowArcs(e.target.checked)} /> Angle arcs</label>
          <span className="ml-auto font-mono text-sm text-slate-400">frame {frame}/{total - 1} · {(frame / fps).toFixed(3)}s</span>
        </div>
        {/* phase timeline */}
        <div className="relative mt-4 h-16 cursor-pointer rounded bg-slate-800"
             onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); seek(Math.round(((e.clientX - r.left) / r.width) * total)) }}>
          <div className="absolute top-0 h-full w-0.5 bg-white" style={{ left: `${(frame / total) * 100}%` }} />
          {report.phases.filter((p) => p.frame != null).map((p, i) => (
            <button key={p.name} title={`${PHASE_LABEL[p.name]} @ ${p.frame} (${p.source}, conf ${p.confidence})`}
                    onClick={(e) => { e.stopPropagation(); seek(p.frame) }}
                    className={`absolute -translate-x-1/2 rounded px-1 text-[10px] font-bold ${p.source === 'manual' ? 'bg-fuchsia-600' : 'bg-sky-600'}`}
                    style={{ left: `${(p.frame / total) * 100}%`, top: `${2 + (i % 3) * 20}px` }}>{SHORT[p.name]}</button>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          Edit phase:
          <select value={editPhase} onChange={(e) => setEditPhase(e.target.value)} className="rounded bg-slate-800 p-1">
            {PHASES.map((p) => <option key={p} value={p}>{PHASE_LABEL[p]}</option>)}
          </select>
          <button disabled={busy} className={btn} onClick={() => savePhase(frame)}>Set to current frame ({frame})</button>
          <button disabled={busy} className={btn} onClick={() => savePhase(null)}>Reset to auto</button>
          {busy && <span className="text-slate-400">recomputing…</span>}
        </div>
      </Card>
      <Card title="Live angles (this frame)">
        {pose && (() => {
          const L = report.legality
          const inWin = L.min_frame != null && frame >= L.min_frame && frame <= (L.br_used ?? L.br_frame ?? -1)
          const a = L.timeline[frame]?.angle
          return (
            <div className="mb-3">
              <VirtualSkeleton lm={pose.frames[frame]?.lm} connections={pose.connections} arm={report.bowling_arm} size={220}
                               accent={inWin ? '#facc15' : '#38bdf8'}
                               sub={inWin && a != null && L.min_angle != null ? `straightened ${Math.max(0, a - L.min_angle).toFixed(1)}° since most-bent (limit 15°)` : 'virtual skeleton · bowling arm highlighted'} />
            </div>
          )
        })()}
        {Object.entries(ang).map(([k, v]) => (
          <div key={k} className="flex justify-between border-b border-slate-800 py-1 text-sm">
            <span className="text-slate-400">{k.replace(/_/g, ' ')}</span>
            <span className="font-mono">{v == null ? <i className="text-slate-500">n/a</i> : `${v.toFixed(1)}°`}</span>
          </div>
        ))}
        <p className="mt-3 text-xs text-slate-500">Joint colour = landmark confidence: green ≥ 0.7, amber ≥ 0.5, red &lt; 0.5 (not used).</p>
      </Card>
    </div>
  )
}
