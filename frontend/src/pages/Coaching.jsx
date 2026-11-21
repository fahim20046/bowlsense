import { useEffect, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Card } from '../components/ui'

export function ScoreCard({ score }) {
  return (
    <Card title="Technique score (transparent rubric)">
      <div className="text-4xl font-bold">{score.total ?? <span className="text-2xl text-slate-500">Unavailable</span>}{score.total != null && <span className="text-base text-slate-400">/100</span>}</div>
      <p className="mb-2 text-xs text-slate-400">Based on {score.available_weight}% of rubric weight{score.partial && ' — partial: some components not measurable from this video'}{score.total == null && ' (needs ≥ 40%)'}.</p>
      {score.components.map((c) => (
        <details key={c.key} className="border-t border-slate-800 py-1 text-sm">
          <summary className="flex cursor-pointer justify-between">
            <span>{c.label} <span className="text-xs text-slate-500">w{c.weight}</span></span>
            <span className="font-mono">{c.score ?? <i className="text-slate-500">n/a</i>}</span>
          </summary>
          <div className="h-1.5 rounded bg-slate-800"><div className="h-1.5 rounded bg-emerald-500" style={{ width: `${c.score ?? 0}%` }} /></div>
          <ul className="mt-1 text-xs text-slate-400">{c.based_on.map((b) => <li key={b}>{b}</li>)}</ul>
        </details>
      ))}
    </Card>
  )
}

export function Coaching({ report }) {
  const P = report.performance
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Top strengths">{P.strengths.length ? <ol className="list-decimal pl-5 text-sm text-emerald-300">{P.strengths.map((s) => <li key={s}>{s}</li>)}</ol> : <p className="text-sm text-slate-500">None measurable from this video.</p>}</Card>
        <Card title="Top improvement areas">{P.improvements.length ? <ol className="list-decimal pl-5 text-sm text-amber-300">{P.improvements.map((s) => <li key={s}>{s}</li>)}</ol> : <p className="text-sm text-slate-500">None flagged from measurable metrics.</p>}</Card>
      </div>
      <Card title="Coaching assistant — highest impact first">
        {P.insights.length === 0 && <p className="text-sm text-slate-500">No insights: too few measurable metrics, or all within target.</p>}
        {P.insights.map((i) => (
          <div key={i.priority} className="border-t border-slate-800 py-2 text-sm">
            <div className="font-semibold">#{i.priority} <span className="text-slate-400">Measured:</span> {i.fact}</div>
            <div><span className="text-slate-400">Impact:</span> {i.impact}</div>
            <div className="text-emerald-300"><span className="text-slate-400">Cue:</span> {i.cue}</div>
            {i.drill && <div className="text-sky-300"><span className="text-slate-400">Drill:</span> {i.drill}</div>}
          </div>
        ))}
        <p className="mt-2 text-xs text-slate-500">Rule-based translation of measured values (no generative AI). Targets are coaching heuristics, not medical or ICC standards.</p>
      </Card>
    </div>
  )
}

const TREND_KEYS = [['technique_score', 'Technique score'], ['front_knee_delta', 'Front knee Δ'], ['release_height_br', 'Release height'],
  ['separation_ffc', 'Hip-shoulder separation'], ['trunk_lateral_br', 'Lateral flexion (BR)'], ['elbow_net_extension', 'Net elbow extension'],
  ['speed_kmh', 'Measured speed'], ['manual_kmh', 'Manual speed']]

export function Compare({ sessions }) {
  const done = sessions.filter((s) => s.status === 'done')
  const [a, setA] = useState(done[1]?.session_id || '')
  const [b, setB] = useState(done[0]?.session_id || '')
  const [rows, setRows] = useState([])
  const [bowler, setBowler] = useState('')
  const [metric, setMetric] = useState('technique_score')
  const [trend, setTrend] = useState(null)
  useEffect(() => { if (a && b && a !== b) api.compare(a, b).then(setRows).catch(() => setRows([])) }, [a, b])
  useEffect(() => { api.trends(metric, bowler).then((t) => setTrend(t[0])).catch(() => setTrend(null)) }, [metric, bowler])
  const label = (s) => `${new Date(s.created_at + 'Z').toLocaleString()} · ${s.bowler_name || '—'} · ${s.perspective}`
  const sel = 'rounded bg-slate-800 p-1 text-sm'
  const bowlers = [...new Set(done.map((s) => s.bowler_name).filter(Boolean))]
  const data = (trend?.points || []).map((p, i) => ({ n: i + 1, date: new Date(p.created_at + 'Z').toLocaleDateString(), value: p.value }))
  return (
    <div className="mt-6 space-y-4">
      <Card title="Compare two deliveries">
        <div className="mb-2 flex flex-wrap gap-2">
          A <select value={a} onChange={(e) => setA(e.target.value)} className={sel}>{done.map((s) => <option key={s.session_id} value={s.session_id}>{label(s)}</option>)}</select>
          B <select value={b} onChange={(e) => setB(e.target.value)} className={sel}>{done.map((s) => <option key={s.session_id} value={s.session_id}>{label(s)}</option>)}</select>
        </div>
        {a === b ? <p className="text-sm text-slate-500">Pick two different sessions.</p> : (
          <div className="max-h-96 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-900 text-left text-xs text-slate-500"><tr><th>Metric</th><th>A</th><th>B</th><th>Δ (B−A)</th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.key} className="border-t border-slate-800">
                  <td className="py-1 pr-2">{r.label}</td>
                  <td className="font-mono">{r.a ?? '—'}</td><td className="font-mono">{r.b ?? '—'}</td>
                  <td className={`font-mono ${r.delta > 0 ? 'text-emerald-400' : r.delta < 0 ? 'text-rose-400' : ''}`}>{r.delta ?? '—'}</td>
                </tr>))}</tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Metric trend over sessions">
        <div className="mb-2 flex flex-wrap gap-2">
          <select value={metric} onChange={(e) => setMetric(e.target.value)} className={sel}>{TREND_KEYS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <select value={bowler} onChange={(e) => setBowler(e.target.value)} className={sel}><option value="">All bowlers</option>{bowlers.map((n) => <option key={n}>{n}</option>)}</select>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ left: -10, right: 10 }}>
            <CartesianGrid stroke="#1e293b" />
            <XAxis dataKey="n" stroke="#94a3b8" fontSize={11} label={{ value: 'session #', position: 'insideBottomRight', offset: -2, fill: '#64748b', fontSize: 10 }} />
            <YAxis stroke="#94a3b8" fontSize={11} />
            <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} formatter={(v) => (v == null ? 'Unavailable' : v)} labelFormatter={(n) => data[n - 1]?.date} />
            <Line dataKey="value" stroke="#34d399" connectNulls={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
        <p className="text-xs text-slate-500">Gaps = sessions where the metric was Unavailable.</p>
      </Card>
    </div>
  )
}
