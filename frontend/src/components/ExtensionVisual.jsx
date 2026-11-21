import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Card } from './ui'
import VirtualSkeleton, { ARM_IDS, elbowAngle } from './VirtualSkeleton'

/** Legality visual: most-bent frame vs release frame as virtual skeletons + Δ gauge + step-through player. */
export default function ExtensionVisual({ id, report }) {
  const L = report.legality, M = L.manual
  const [pose, setPose] = useState(null)
  const [cur, setCur] = useState(null)
  const [playing, setPlaying] = useState(false)
  useEffect(() => { api.pose(id).then(setPose) }, [id])

  // source of the verdict: manual clicks if present, otherwise automatic
  const src = useMemo(() => {
    if (M) {
      const byFrame = Object.fromEntries(M.inputs.map((p) => [p.frame, [p.shoulder, p.elbow, p.wrist]]))
      const minP = M.points.reduce((a, b) => (b.angle < a.angle ? b : a))
      return { minF: minP.frame, relF: M.br_frame, startF: M.horizontal_frame, delta: M.net_extension, manual: byFrame }
    }
    if (L.min_frame == null || L.br_used == null) return null
    return { minF: L.min_frame, relF: L.br_used, startF: L.horizontal_frame ?? L.min_frame, delta: L.net_extension, manual: {} }
  }, [L, M])

  useEffect(() => { if (src) setCur(src.startF) }, [src])
  useEffect(() => {
    if (!playing || !src) return
    const t = setInterval(() => setCur((f) => (f >= src.relF + 6 ? src.startF - 4 : f + 1)), 220)
    return () => clearInterval(t)
  }, [playing, src])

  if (!src) {
    return (
      <Card title="Elbow extension — visual">
        <p className="text-sm text-slate-400">No elbow extension measured yet for this delivery ({L.final_classification}). Use Manual elbow verification below, or check the release frame in Video Studio.</p>
      </Card>
    )
  }
  if (!pose) return <Card title="Elbow extension — visual"><p className="text-sm text-slate-400">Loading skeleton…</p></Card>

  const lmAt = (f) => pose.frames[f]?.lm || null
  const angleAt = (f) => {
    if (src.manual[f]) return elbowAngle(...src.manual[f])
    const a = L.timeline[f]?.angle
    return a ?? null
  }
  const minAng = angleAt(src.minF), relAng = angleAt(src.relF)
  const delta = src.delta
  const illegal = delta >= 15
  const pct = Math.min(100, (Math.max(0, delta) / 30) * 100)
  const curAng = cur != null ? angleAt(cur) : null
  const lo = src.startF - 4, hi = src.relF + 6

  return (
    <Card title="Elbow extension — visual" right={<span className="text-xs text-slate-400">{M ? 'from your manual clicks' : 'automatic skeleton'}</span>}>
      <div className="grid items-center gap-4 md:grid-cols-[1fr_auto_1fr]">
        <VirtualSkeleton lm={lmAt(src.minF)} connections={pose.connections} arm={report.bowling_arm} armOverride={src.manual[src.minF]}
                         title="Most bent (before release)" sub={`frame ${src.minF} · elbow ${minAng?.toFixed(1) ?? '—'}°`} accent="#f472b6" />
        <div className="mx-auto w-56 text-center">
          <div className="text-xs uppercase tracking-wider text-slate-400">Elbow straightening</div>
          <div className={`text-5xl font-extrabold tracking-tight ${illegal ? 'text-rose-400' : 'text-emerald-400'}`}>{delta}°</div>
          <div className="text-xs text-slate-400">{relAng?.toFixed(1)}° − {minAng?.toFixed(1)}°</div>
          <div className="relative mt-4 h-3 rounded-full bg-gradient-to-r from-emerald-600 via-emerald-500 to-rose-600">
            <div className="absolute -top-1 h-5 w-0.5 bg-white" style={{ left: '50%' }} />
            <div className="absolute -top-2 h-7 w-3 -translate-x-1/2 rounded bg-white shadow" style={{ left: `${pct}%` }} />
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-slate-400"><span>0°</span><span>15° limit</span><span>30°+</span></div>
          <div className={`mt-3 inline-block rounded-lg px-3 py-1 text-sm font-bold ${illegal ? 'bg-rose-600' : 'bg-emerald-600'} text-white`}>{illegal ? 'Illegal' : 'Legal'}</div>
        </div>
        <VirtualSkeleton lm={lmAt(src.relF)} connections={pose.connections} arm={report.bowling_arm} armOverride={src.manual[src.relF]}
                         title="Ball release" sub={`frame ${src.relF} · elbow ${relAng?.toFixed(1) ?? '—'}°`} accent="#38bdf8" />
      </div>

      <div className="mt-6 grid items-center gap-4 border-t border-slate-800 pt-5 md:grid-cols-[auto_1fr]">
        <VirtualSkeleton lm={lmAt(cur)} connections={pose.connections} arm={report.bowling_arm} armOverride={src.manual[cur]} size={260}
                         title="Step through the delivery" accent={cur >= src.startF && cur <= src.relF ? '#facc15' : '#64748b'} />
        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-2">
            <button className="rounded-lg bg-emerald-600 px-3 py-1.5 font-medium text-white hover:bg-emerald-500" onClick={() => setPlaying(!playing)}>{playing ? '❚❚ Pause' : '▶ Play'}</button>
            <button className="rounded-lg bg-slate-800 px-3 py-1.5" onClick={() => { setPlaying(false); setCur(Math.max(lo, cur - 1)) }}>◀</button>
            <button className="rounded-lg bg-slate-800 px-3 py-1.5" onClick={() => { setPlaying(false); setCur(Math.min(hi, cur + 1)) }}>▶</button>
            <span className="font-mono text-slate-300">frame {cur}</span>
          </div>
          <input type="range" min={lo} max={hi} value={cur ?? lo} onChange={(e) => { setPlaying(false); setCur(+e.target.value) }} className="w-full accent-emerald-500" />
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-lg bg-slate-900/60 p-2"><div className="text-[10px] uppercase text-slate-400">Elbow angle</div><div className="font-mono text-lg">{curAng == null ? '—' : `${curAng.toFixed(1)}°`}</div></div>
            <div className="rounded-lg bg-slate-900/60 p-2"><div className="text-[10px] uppercase text-slate-400">Straightened so far</div>
              <div className="font-mono text-lg">{curAng == null || minAng == null || cur < src.minF ? '—' : `${Math.max(0, curAng - minAng).toFixed(1)}°`}</div></div>
            <div className="rounded-lg bg-slate-900/60 p-2"><div className="text-[10px] uppercase text-slate-400">Phase</div>
              <div className="text-sm">{cur < src.startF ? 'before arm horizontal' : cur <= src.relF ? 'arm horizontal → release' : 'after release'}</div></div>
          </div>
          <p className="text-xs text-slate-400">Pink wedge = how far the forearm is bent away from the dashed straight-arm line. Legality compares the most-bent frame with release: under 15° of straightening = Legal.</p>
        </div>
      </div>
    </Card>
  )
}
