import { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Kpi } from '../components/ui'
import { LegalityBadge } from './Screening'

const pct = (v) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
const VIEW = { side_on: 'Side-on', front_on: 'Front-on', rear: 'Rear' }

function Matrix({ s }) {
  const cell = (n, good, label) => (
    <div className={`rounded-md border-2 p-3 text-center ${good ? 'border-emerald-500 bg-emerald-950' : 'border-rose-500 bg-rose-950'}`}>
      <div className="text-4xl font-extrabold">{n}</div>
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</div>
    </div>
  )
  return (
    <div className="grid grid-cols-[auto_1fr_1fr] items-center gap-2 text-sm">
      <div />
      <div className="text-center font-display font-bold uppercase text-slate-300">App: Illegal</div>
      <div className="text-center font-display font-bold uppercase text-slate-300">App: Legal</div>
      <div className="pr-2 text-right font-display font-bold uppercase text-slate-300">Expert:<br />Illegal</div>
      {cell(s.TP_illegal_caught, true, 'illegal caught')}
      {cell(s.FN_illegal_missed, false, 'illegal missed')}
      <div className="pr-2 text-right font-display font-bold uppercase text-slate-300">Expert:<br />Legal</div>
      {cell(s.FP_legal_flagged, false, 'false alarm')}
      {cell(s.TN_legal_ok, true, 'legal passed')}
    </div>
  )
}

function ReleaseBars({ r }) {
  const rows = [['Rule only', r.rule_only], ['Trained model only', r.model_only], ['Rule + model (used in app)', r.hybrid_app]]
  return (
    <div className="space-y-3">
      {rows.map(([label, m]) => m && (
        <div key={label}>
          <div className="flex justify-between text-sm"><span>{label}</span>
            <span className="font-mono">{pct(m.within_2)} within ±2 frames · median error {m.median_abs_err_frames ?? '—'} f</span></div>
          <div className="mt-1 h-3 rounded-sm bg-slate-800">
            <div className={`h-3 rounded-sm ${label.startsWith('Rule +') ? 'bg-emerald-500' : 'bg-slate-500'}`} style={{ width: `${(m.within_2 || 0) * 100}%` }} />
          </div>
        </div>
      ))}
      <p className="text-xs text-slate-400">{r.test_deliveries} held-out test deliveries from videos never used for training.</p>
    </div>
  )
}

export default function Validation() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.validation().then(setData).catch((e) => setErr(e.message)) }, [])
  if (err) return <p className="text-rose-400">{err}</p>
  if (!data) return <p className="text-slate-400">Loading validation results…</p>
  const L = data.legality, s = L?.summary
  return (
    <div className="space-y-5">
      <div>
        <div className="font-display text-sm font-bold uppercase tracking-[0.3em] text-[var(--color-ball)]">tested against expert labels</div>
        <h2 className="font-display text-4xl font-extrabold uppercase tracking-tight">How accurate is BowlSense?</h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          Every clip below went through exactly the same pipeline as an uploaded video — bowler tracking, pose,
          release detection and the 15° elbow rule — and the app's verdict was compared with the expert's label.
        </p>
      </div>

      {s ? (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Kpi label="Overall accuracy" sub={`${s.TP_illegal_caught + s.TN_legal_ok} of ${s.decided} clips correct`}>
              <div className="text-5xl font-extrabold">{pct(s.accuracy_on_decided)}</div>
            </Kpi>
            <Kpi label="Illegal actions caught" sub={`${s.TP_illegal_caught} of ${s.TP_illegal_caught + s.FN_illegal_missed} illegal clips`}>
              <div className="text-5xl font-extrabold text-emerald-400">{pct(s.illegal_recall)}</div>
            </Kpi>
            <Kpi label="Legal actions passed" sub={`${s.TN_legal_ok} of ${s.TN_legal_ok + s.FP_legal_flagged} legal clips`}>
              <div className="text-5xl font-extrabold text-emerald-400">{pct(s.legal_specificity)}</div>
            </Kpi>
          </div>

          <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
            <Card title="Confusion matrix">
              <Matrix s={s} />
              <p className="mt-3 text-xs text-slate-400">Rule: net elbow straightening from arm-horizontal (delivery upswing) to release ≥ 15° → Illegal.</p>
            </Card>
            <Card title="Every clip">
              <div className="max-h-96 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-[#fffdf8] text-left text-slate-500">
                    <tr><th className="py-1">Clip</th><th>Expert</th><th>App</th><th>Straightening</th><th>View</th><th /></tr>
                  </thead>
                  <tbody>
                    {L.rows.map((r) => {
                      const ok = r.verdict.toLowerCase() === r.label
                      return (
                        <tr key={r.video} className={`border-t border-slate-800 ${ok ? '' : 'bg-rose-950'}`}>
                          <td className="py-1 font-mono">#{r.video}</td>
                          <td className="capitalize">{r.label}</td>
                          <td><LegalityBadge c={r.verdict} /></td>
                          <td className="font-mono">{r.net_extension == null ? '—' : `${r.net_extension}°`}</td>
                          <td className="text-slate-400">{VIEW[r.view] || r.view}</td>
                          <td className={`font-bold ${ok ? 'text-emerald-400' : 'text-rose-400'}`}>{ok ? '✓' : '✗'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </>
      ) : <Card title="Legality"><p className="text-sm text-slate-400">No legality evaluation found — run training/evaluate_legality.py.</p></Card>}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Trained release-frame detector">
          {data.release ? <ReleaseBars r={data.release} /> : <p className="text-sm text-slate-400">No release evaluation found.</p>}
        </Card>
        <Card title="Data & honest caveats">
          <ul className="space-y-2 text-sm">
            <li><b>Legality data:</b> {data.legality_dataset.name} — {data.legality_dataset.license} licence ·{' '}
              <a className="text-sky-400 underline" href={data.legality_dataset.source} target="_blank" rel="noreferrer">dataset</a> ·{' '}
              <a className="text-sky-400 underline" href={data.legality_dataset.paper} target="_blank" rel="noreferrer">paper</a></li>
            <li><b>Release data:</b> {data.release_dataset.name}, split {data.release_dataset.split}.</li>
            <li>2D single-camera video at 30 fps: most errors come from front-on clips and borderline values near 15°.</li>
            <li>One rule fix (measure from the delivery upswing, not the gather) was found while inspecting this dataset; it follows the ICC definition rather than a tuned number. A separate, unseen test set would make the result stronger.</li>
            <li>Educational project — not an official ICC assessment.</li>
          </ul>
        </Card>
      </div>
    </div>
  )
}
