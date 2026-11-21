import { useState } from 'react'
import { api } from '../api'
import { Card, MetricValue } from '../components/ui'

const STATUS = {
  ok: 'Measured from calibrated ball tracking',
  unavailable_perspective: 'Unavailable — ball-tracking speed needs a side-on camera',
  unavailable_no_calibration: 'Unavailable — pitch calibration missing',
  unavailable_tracking_failed: 'Unavailable — ball could not be tracked reliably',
}
const LVL = { High: 'text-emerald-400', Moderate: 'text-amber-400', Low: 'text-rose-400', Unavailable: 'text-slate-500' }

function Calibrate({ id, report, onReport }) {
  const br = report.phases.find((p) => p.name === 'br')?.frame ?? 0
  const [frame, setFrame] = useState(report.speed.calibration?.frame ?? br)
  const [pts, setPts] = useState([])
  const [err, setErr] = useState('')
  const W = report.meta.width, H = report.meta.height
  const click = (e) => {
    if (pts.length >= 2) return
    const r = e.currentTarget.getBoundingClientRect()
    setPts([...pts, [((e.clientX - r.left) / r.width) * W, ((e.clientY - r.top) / r.height) * H]])
  }
  const save = async (body) => {
    setErr('')
    try { onReport(await api.setCalibration(id, body)); setPts([]) } catch (x) { setErr(x.message) }
  }
  const shown = pts.length ? pts : report.speed.calibration ? [report.speed.calibration.p1, report.speed.calibration.p2] : []
  return (
    <Card title="2-point pitch calibration (popping creases = 17.68 m)">
      <p className="mb-2 text-xs text-slate-400">Click <b>1)</b> the bowler's-end popping crease, then <b>2)</b> the batter's-end popping crease, on the same line along the pitch.</p>
      <div className="relative cursor-crosshair" onClick={click}>
        <img src={api.frameUrl(id, frame)} className="w-full rounded" draggable={false} />
        <svg viewBox={`0 0 ${W} ${H}`} className="pointer-events-none absolute inset-0 h-full w-full">
          {shown.length === 2 && <line x1={shown[0][0]} y1={shown[0][1]} x2={shown[1][0]} y2={shown[1][1]} stroke="#e879f9" strokeWidth={3} />}
          {shown.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={8} fill="none" stroke="#e879f9" strokeWidth={3} />)}
        </svg>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        Frame <input type="number" value={frame} min={0} max={report.meta.total_frames - 1} onChange={(e) => { setFrame(+e.target.value); setPts([]) }} className="w-20 rounded bg-slate-800 p-1" />
        <button disabled={pts.length !== 2} className="rounded bg-emerald-700 px-3 py-1 disabled:opacity-40" onClick={() => save({ frame, p1: pts[0], p2: pts[1], distance_m: 17.68 })}>Save calibration</button>
        <button className="rounded bg-slate-800 px-3 py-1" onClick={() => setPts([])}>Reset clicks</button>
        {report.speed.calibration && <button className="rounded bg-slate-800 px-3 py-1" onClick={() => save(null)}>Remove calibration</button>}
        {err && <span className="text-rose-400">{err}</span>}
      </div>
    </Card>
  )
}

function Manual({ id, report, onReport }) {
  const br = report.phases.find((p) => p.name === 'br')?.frame ?? 0
  const m = report.speed.manual
  const [rel, setRel] = useState(m?.release_frame ?? br)
  const [arr, setArr] = useState(m?.arrival_frame ?? br + 15)
  const [err, setErr] = useState('')
  const save = async (body) => { setErr(''); try { onReport(await api.setManual(id, body)) } catch (x) { setErr(x.message) } }
  return (
    <Card title="Manual timing fallback (any camera view)">
      <p className="mb-2 text-xs text-slate-400">Use Video Studio's frame stepping to find the release frame and the frame the ball reaches the batter's popping crease.</p>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        Release <input type="number" value={rel} onChange={(e) => setRel(+e.target.value)} className="w-20 rounded bg-slate-800 p-1" />
        Arrival <input type="number" value={arr} onChange={(e) => setArr(+e.target.value)} className="w-20 rounded bg-slate-800 p-1" />
        <button className="rounded bg-emerald-700 px-3 py-1" onClick={() => save({ release_frame: rel, arrival_frame: arr })}>Compute</button>
        {m && <button className="rounded bg-slate-800 px-3 py-1" onClick={() => save(null)}>Clear</button>}
        {err && <span className="text-rose-400">{err}</span>}
      </div>
      <p className="mt-2 text-sm">Manual average speed: <b className="font-mono">{report.speed.manual_kmh != null ? `${report.speed.manual_kmh} km/h` : 'Unavailable'}</b></p>
    </Card>
  )
}

export default function Speed({ id, report, onReport }) {
  const S = report.speed, P = report.speed_potential
  const all = [...report.biomechanics.upper_body]
  const rel = ['release_height_br', 'wrist_offset_br', 'arm_ang_speed'].map((k) => all.find((m) => m.key === k)).filter(Boolean)
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Measured ball speed">
          <div className="text-4xl font-bold">{S.measured_kmh != null ? <>{S.measured_kmh}<span className="text-base text-slate-400"> km/h</span></> : <span className="text-2xl text-slate-500">Measured Speed: Unavailable</span>}</div>
          <p className="mt-1 text-sm text-slate-400">{STATUS[S.status] || S.status}</p>
          <p className="text-xs text-slate-500">Ball detections: {S.detections} · linearity R²: {S.fit_r2 ?? '—'}</p>
          <ul className="mt-2 list-disc pl-5 text-xs text-slate-400">{S.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </Card>
        <Card title="Biomechanical speed-potential indicator">
          <div className={`text-3xl font-bold ${LVL[P.level]}`}>{P.level}</div>
          <p className="mb-2 text-xs text-amber-300">{P.note}</p>
          {P.components.map((m) => (
            <div key={m.key} className="border-t border-slate-800 py-1 text-sm">
              <div className="flex justify-between"><span>{m.label}</span><MetricValue m={m} /></div>
              <div className="h-1.5 rounded bg-slate-800"><div className="h-1.5 rounded bg-sky-500" style={{ width: `${(P.scores[m.key] ?? 0) * 100}%` }} /></div>
            </div>
          ))}
        </Card>
      </div>
      <Card title="Release point">
        <div className="grid gap-2 text-sm md:grid-cols-3">
          {rel.map((m) => <div key={m.key}>{m.label}<br /><MetricValue m={m} /></div>)}
        </div>
        <p className="mt-2 text-xs text-slate-500">Delivery-to-delivery consistency is compared across sessions in History (Milestone 4).</p>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Calibrate id={id} report={report} onReport={onReport} />
        <Manual id={id} report={report} onReport={onReport} />
      </div>
    </div>
  )
}
