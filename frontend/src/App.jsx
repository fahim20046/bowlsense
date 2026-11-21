import { useCallback, useEffect, useState } from 'react'
import { api, PHASE_LABEL } from './api'
import { Card, Gauge, Kpi, Seam } from './components/ui'
import Upload from './pages/Upload'
import Studio from './pages/Studio'
import Report from './pages/Report'
import { ConfidenceChip, Injury, Legality, LegalityBadge } from './pages/Screening'
import Speed from './pages/Speed'
import Validation from './pages/Validation'
import { Coaching, Compare, ScoreCard } from './pages/Coaching'

const TABS = [['overview', 'Overview'], ['studio', 'Video Studio'], ['report', 'Biomechanics'], ['legality', 'Legality'], ['injury', 'Injury Stress'], ['speed', 'Speed'], ['coaching', 'Coaching']]

const VIEW = { side_on: 'Side-on', front_on: 'Front-on', rear: 'Rear' }

function SettingsCard({ report, onReport }) {
  const [view, setView] = useState(report.perspective)
  const [arm, setArm] = useState(report.bowling_arm)
  const [busy, setBusy] = useState(false)
  const det = report.detected_perspective
  const mismatch = det && det !== report.perspective
  const apply = async () => {
    setBusy(true)
    try { onReport(await api.setSettings(report.session_id, { perspective: view, bowling_arm: arm })) } finally { setBusy(false) }
  }
  const sel = 'rounded bg-slate-800 p-1 text-sm'
  return (
    <Card title="Camera view & bowling arm" className={`md:col-span-2 ${mismatch ? 'border-amber-500' : ''}`}>
      {mismatch && <p className="mb-2 text-sm text-amber-300">⚠ The video looks <b>{VIEW[det]}</b> but <b>{VIEW[report.perspective]}</b> was selected. Most metrics depend on the view.</p>}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        View <select value={view} onChange={(e) => setView(e.target.value)} className={sel}>{Object.entries(VIEW).map(([k, l]) => <option key={k} value={k}>{l}{k === det ? ' (detected)' : ''}</option>)}</select>
        Arm <select value={arm} onChange={(e) => setArm(e.target.value)} className={sel}><option value="right">Right</option><option value="left">Left</option></select>
        <button disabled={busy || (view === report.perspective && arm === report.bowling_arm)} onClick={apply} className="rounded bg-emerald-700 px-3 py-1 disabled:opacity-40">{busy ? 'Re-analysing…' : 'Apply & re-analyse'}</button>
        {mismatch && view !== det && <button onClick={() => setView(det)} className="rounded bg-amber-700 px-3 py-1">Use detected ({VIEW[det]})</button>}
      </div>
    </Card>
  )
}

function Overview({ report, onReport }) {
  const q = report.quality, L = report.legality, inj = report.injury.flags
  const ext = L.manual?.net_extension ?? L.net_extension
  const count = (lv) => inj.filter((f) => f.level === lv).length
  const phases = report.phases.filter((p) => p.frame != null && p.name !== 'run_up')
  // zoom the strip to the delivery window (gather → follow-through) so markers don't bunch up
  const fs = phases.map((p) => p.frame)
  const span = fs.length ? Math.max(...fs) - Math.min(...fs) : 1
  const lo = fs.length ? Math.max(0, Math.min(...fs) - Math.max(5, span * 0.15)) : 0
  const hi = fs.length ? Math.min(report.meta.total_frames, Math.max(...fs) + Math.max(5, span * 0.15)) : report.meta.total_frames
  const pos = (f) => ((f - lo) / (hi - lo)) * 100
  return (
    <div className="space-y-5">
      {/* KPI row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Technique score" accent="from-emerald-500/25" sub={`${report.score.available_weight}% of rubric measurable`}>
          <div className="flex justify-center"><Gauge value={report.score.total} size={112} label="/ 100" /></div>
        </Kpi>
        <Kpi label="Legality (elbow extension)" accent={L.final_classification === 'Illegal' ? 'from-rose-500/30' : 'from-emerald-500/25'}
             sub={L.final_source === 'manual' ? 'Manually verified' : 'Automatic estimate'}>
          <div className="mb-2 flex flex-wrap items-center gap-1.5"><LegalityBadge c={L.final_classification} />
            {L.final_source !== 'manual' && <ConfidenceChip level={L.confidence_level} />}</div>
          <div className="text-3xl font-extrabold tracking-tight">{ext == null ? '—' : `${ext}°`}</div>
          <div className="text-xs text-slate-400">limit 15°</div>
        </Kpi>
        <Kpi label="Video quality" accent="from-sky-500/25" sub={`${report.meta.width}×${report.meta.height} · ${report.meta.fps.toFixed(0)} fps`}>
          <div className="text-4xl font-extrabold tracking-tight">{q.score}<span className="text-base font-medium text-slate-500"> /100</span></div>
          <div className="mt-2 h-1.5 rounded-full bg-slate-800"><div className="h-1.5 rounded-full bg-gradient-to-r from-sky-500 to-emerald-400" style={{ width: `${q.score}%` }} /></div>
          <div className="mt-2 text-xs text-slate-400">Bowler tracked {(q.detection_rate * 100).toFixed(0)}% · visibility {q.mean_visibility}</div>
        </Kpi>
        <Kpi label="Injury stress screening" accent={count('High concern') ? 'from-rose-500/30' : 'from-amber-500/25'}>
          {[['High concern', 'bg-rose-500', 'High'], ['Moderate concern', 'bg-amber-500', 'Moderate'], ['Low concern', 'bg-emerald-500', 'Low']].map(([lv, c, t]) => (
            <div key={lv} className="flex items-center gap-2 py-0.5 text-sm">
              <span className={`h-2.5 w-2.5 rounded-full ${c}`} /><span className="text-slate-300">{t}</span>
              <span className="ml-auto font-mono text-lg font-bold">{count(lv)}</span>
            </div>
          ))}
        </Kpi>
      </div>

      <SettingsCard key={report.perspective + report.bowling_arm} report={report} onReport={onReport} />

      {/* phase strip */}
      <Card title="Delivery phases">
        <div className="mb-1 flex justify-between text-[10px] uppercase tracking-wider text-slate-500"><span>frame {Math.round(lo)}</span><span>delivery window</span><span>frame {Math.round(hi)}</span></div>
        <div className="relative mt-7 mb-10 h-2 rounded-full bg-gradient-to-r from-sky-600/40 via-emerald-500/50 to-emerald-400/70">
          {phases.map((p, i) => (
            <div key={p.name} className="absolute -translate-x-1/2" style={{ left: `${pos(p.frame)}%`, top: -6 }}>
              <div className={`h-5 w-5 rounded-full border-2 ${p.source === 'manual' ? 'border-fuchsia-400 bg-fuchsia-900' : 'border-emerald-400 bg-slate-900'}`} title={`${PHASE_LABEL[p.name]} · frame ${p.frame}`} />
              <div className={`absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] font-semibold text-slate-300 ${['-top-5', 'top-6', '-top-9', 'top-10'][i % 4]}`}>{p.name === 'follow_through' ? 'FT' : p.name.toUpperCase()}</div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm md:grid-cols-3">
          {report.phases.map((p) => (
            <div key={p.name} className="flex justify-between border-b border-slate-800/60 py-1">
              <span className="text-slate-400">{PHASE_LABEL[p.name]}</span>
              <span className="font-mono">{p.frame == null ? <i className="text-slate-500">—</i> : <>#{p.frame} <span className="text-slate-500">{p.t}s</span></>}</span>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-5 md:grid-cols-2">
        <ScoreCard score={report.score} />
        <Card title="Top recommendations">
          {report.performance.insights.slice(0, 3).map((i) => (
            <div key={i.priority} className="mb-3 flex gap-3 rounded-xl bg-slate-900/50 p-3 text-sm">
              <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-emerald-500/15 font-bold text-emerald-300">{i.priority}</div>
              <div><div className="text-slate-300">{i.fact}</div><div className="mt-1 text-emerald-300">→ {i.cue}</div></div>
            </div>
          ))}
          {report.performance.insights.length === 0 && <p className="text-sm text-slate-500">No recommendations from measurable metrics.</p>}
        </Card>
      </div>
      {report.warnings.length > 0 && (
        <Card title="Notes & warnings">
          <ul className="space-y-1 text-sm text-amber-200/90">{report.warnings.map((w) => <li key={w} className="flex gap-2"><span>⚠</span>{w}</li>)}</ul>
        </Card>
      )}
    </div>
  )
}

function History({ onOpen }) {
  const [rows, setRows] = useState([])
  const load = () => api.list().then(setRows)
  useEffect(() => { load() }, [])
  // keep refreshing while any session is (re)processing
  useEffect(() => {
    if (!rows.some((s) => s.status === 'queued' || s.status === 'processing')) return
    const t = setTimeout(load, 3000)
    return () => clearTimeout(t)
  }, [rows])
  return (<>
    <Card title="Sessions" className="mt-6">
      {rows.length === 0 && <p className="text-sm text-slate-500">No sessions yet.</p>}
      {rows.map((s) => (
        <div key={s.session_id} className="mb-2 flex flex-wrap items-center gap-3 rounded-xl border border-slate-800/70 bg-slate-900/40 px-4 py-3 text-sm hover:border-slate-700">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-slate-800 font-mono text-sm font-bold text-emerald-300">{s.technique_score != null ? Math.round(s.technique_score) : '—'}</span>
          <div>
            <div className="font-semibold">{s.bowler_name || 'Unnamed bowler'}</div>
            <div className="text-xs text-slate-400">{new Date(s.created_at + 'Z').toLocaleString()} · {s.bowling_arm}-arm · {s.perspective.replace('_', '-')}</div>
          </div>
          {s.legality_class && s.status === 'done' && <LegalityBadge c={s.legality_class} />}
          {s.status !== 'done' && <span className={s.status === 'failed' ? 'text-rose-400' : 'text-slate-400'}>{s.status}</span>}
          <div className="ml-auto flex gap-2">
            {s.status === 'done' && <button className="rounded-lg bg-emerald-600 px-3 py-1 font-medium text-white hover:bg-emerald-500" onClick={() => onOpen(s.session_id)}>Open</button>}
            {(s.status === 'done' || s.status === 'failed') && (
              <button className="rounded-lg px-3 py-1 text-sky-300 hover:bg-sky-500/10" title="Re-run bowler tracking and pose detection on this video (keeps your settings)"
                      onClick={() => api.reprocess(s.session_id).then(load)}>Re-track</button>
            )}
            <button className="rounded-lg px-3 py-1 text-rose-400 hover:bg-rose-500/10" onClick={() => api.remove(s.session_id).then(load)}>Delete</button>
          </div>
        </div>
      ))}
    </Card>
    {rows.filter((s) => s.status === 'done').length >= 2 && <Compare sessions={rows} />}
  </>)
}

export default function App() {
  const [showVal, setShowVal] = useState(() => location.hash === '#validation')
  const [id, setId] = useState(() => (location.hash === '#validation' ? null : location.hash.slice(1) || null))
  const [report, setReport] = useState(null)
  const [tab, setTab] = useState('overview')
  const [err, setErr] = useState('')

  const open = useCallback((sid) => { location.hash = sid; setShowVal(false); setId(sid); setTab('overview') }, [])
  const home = () => { location.hash = ''; setShowVal(false); setId(null) }
  const openValidation = () => { location.hash = 'validation'; setId(null); setShowVal(true) }
  useEffect(() => {
    setReport(null); setErr('')
    if (id) api.analysis(id).then(setReport).catch((e) => setErr(e.message))
  }, [id])

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b-[3px] border-[var(--color-ink)] bg-[var(--color-ball)] text-[#fff6e8]">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-2.5">
          <button onClick={home} className="flex items-center gap-2.5">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-[#fff6e8] shadow-[2px_2px_0_var(--color-ink)]"><Seam size={28} /></span>
            <span className="text-left leading-none">
              <span className="block font-display text-2xl font-extrabold uppercase tracking-wide">BowlSense</span>
              <span className="block font-display text-[11px] font-semibold uppercase tracking-[0.25em] text-[#ffd9cf]">bowling action lab</span>
            </span>
          </button>
          {id && report && (
            <span className="hidden border-l-2 border-[#ffd9cf]/60 pl-3 font-display text-sm font-semibold uppercase tracking-wider md:inline">
              {report.bowling_arm === 'right' ? 'Right' : 'Left'}-arm · {{ side_on: 'Side-on', front_on: 'Front-on', rear: 'Rear' }[report.perspective]} · {report.meta.duration_s.toFixed(1)} s
            </span>
          )}
          <button className={`ml-auto rounded-sm border-2 border-[#fff6e8] px-3 py-1 font-display text-sm font-bold uppercase tracking-wider ${showVal ? 'bg-[#fff6e8] text-[var(--color-ball)]' : 'text-[#fff6e8] hover:bg-[#fff6e8] hover:text-[var(--color-ball)]'}`}
                  onClick={openValidation}>Validation</button>
          <button className="rounded-sm border-2 border-[#fff6e8] bg-[#fff6e8] px-3 py-1 font-display text-sm font-bold uppercase tracking-wider text-[var(--color-ball)] hover:bg-transparent hover:text-[#fff6e8]"
                  onClick={home}>New delivery / History</button>
        </div>
        {id && (
          <nav className="bg-[var(--color-ink)]">
            <div className="mx-auto flex max-w-7xl gap-0 overflow-x-auto px-4">
              {TABS.map(([k, l]) => (
                <button key={k} onClick={() => setTab(k)}
                        className={`whitespace-nowrap border-b-[3px] px-4 py-2 font-display text-[15px] font-semibold uppercase tracking-wider ${tab === k ? 'border-[#f2c14e] text-[#f2c14e]' : 'border-transparent text-[#d9d4c7] hover:text-white'}`}>
                  {l}
                </button>
              ))}
            </div>
          </nav>
        )}
      </header>
      <main className="mx-auto max-w-7xl p-4 md:p-6">
      {showVal && <Validation />}
      {!id && !showVal && (
        <div className="mb-8 mt-2 text-center">
          <div className="font-display text-sm font-bold uppercase tracking-[0.3em] text-[var(--color-ball)]">upload · track · measure · coach</div>
          <h2 className="mt-1 font-display text-5xl font-extrabold uppercase tracking-tight text-[var(--color-ink)] md:text-6xl">Break down the delivery</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-slate-400">Drop in a bowling clip — get the phases, the elbow straightening against the 15° line, stress flags, speed and coaching cues.</p>
        </div>
      )}
      {!id && !showVal && <><Upload onDone={open} /><History onOpen={open} /></>}
      {id && !report && !err && <div className="py-20 text-center text-slate-400">Loading analysis…</div>}
      {err && <p className="text-rose-400">{err}</p>}
      {id && report && tab === 'overview' && <Overview report={report} onReport={setReport} />}
      {id && report && tab === 'studio' && <Studio id={id} report={report} onReport={setReport} />}
      {id && report && tab === 'report' && <Report report={report} />}
      {id && report && tab === 'legality' && <Legality id={id} report={report} onReport={setReport} />}
      {id && report && tab === 'injury' && <Injury report={report} />}
      {id && report && tab === 'speed' && <Speed id={id} report={report} onReport={setReport} />}
      {id && report && tab === 'coaching' && <Coaching report={report} />}
      </main>
    </div>
  )
}
