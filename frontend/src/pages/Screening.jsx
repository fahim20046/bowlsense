import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card } from '../components/ui'
import ManualElbow from '../components/ManualElbow'
import ExtensionVisual from '../components/ExtensionVisual'

const LEGAL_COLOR = {
  Legal: 'bg-emerald-700 text-white',
  Illegal: 'bg-rose-700 text-white',
  'No obvious concern detected': 'bg-emerald-800 text-emerald-200',
  'Further assessment recommended': 'bg-amber-800 text-amber-100',
  'Potential legality concern': 'bg-rose-800 text-rose-100',
  Unavailable: 'bg-slate-700 text-slate-300',
}
const CONF = {
  high: ['bg-emerald-800 text-emerald-200', 'High confidence', 'Clean, full-length arm on enough frames.'],
  medium: ['bg-amber-800 text-amber-200', 'Medium confidence', 'Standard arm-length check only — partly foreshortened view.'],
  low: ['bg-rose-800 text-rose-200', 'Low-confidence estimate', 'Few usable elbow frames; only obvious landmark errors removed. Verify manually.'],
}
export const ConfidenceChip = ({ level }) => level && CONF[level]
  ? <span title={CONF[level][2]} className={`rounded px-2 py-0.5 text-xs font-semibold ${CONF[level][0]}`}>{CONF[level][1]}</span>
  : null

export const LegalityBadge =({ c }) => <span className={`rounded px-2 py-1 text-sm font-semibold ${LEGAL_COLOR[c] || LEGAL_COLOR.Unavailable}`}>{c}</span>

const Disclaimer = ({ children }) => (
  <div className="rounded-lg border border-amber-700 bg-amber-950/50 p-3 text-sm text-amber-200">⚠ {children}</div>
)
const num = (v, u = '°') => (v == null ? <i className="text-slate-500">Unavailable</i> : `${v}${u}`)

export function Legality({ id, report, onReport }) {
  const L = report.legality
  const M = L.manual
  const ffc = report.phases.find((p) => p.name === 'ffc')?.frame
  const manualAt = Object.fromEntries((M?.points || []).map((p) => [p.frame, p.angle]))
  const data = L.timeline.map((p) => ({ frame: p.frame, angle: p.angle, manual: manualAt[p.frame] ?? null }))
  return (
    <div className="space-y-4">
      <Disclaimer>{L.disclaimer}</Disclaimer>
      <Card title="Final screening result">
        <div className="flex flex-wrap items-center gap-3">
          <LegalityBadge c={L.final_classification} />
          <span className={`rounded px-2 py-0.5 text-xs ${L.final_source === 'manual' ? 'bg-fuchsia-800 text-fuchsia-100' : 'bg-slate-700 text-slate-300'}`}>
            {L.final_source === 'manual' ? 'Manually verified (digitised joints)' : 'Automatic estimate'}</span>
          {L.final_source !== 'manual' && <ConfidenceChip level={L.confidence_level} />}
        </div>
        {M && (
          <div className="mt-3 grid grid-cols-2 gap-2 text-sm md:grid-cols-5">
            <div>Arm horizontal<br /><b>{M.points[0].angle}°</b> <span className="text-slate-500">#{M.horizontal_frame}</span></div>
            <div>Min elbow angle<br /><b>{M.min_angle}°</b></div>
            <div>At release<br /><b>{M.angle_at_br}°</b> <span className="text-slate-500">#{M.br_frame}</span></div>
            <div>Net extension Δθ<br /><b>{M.net_extension}°</b></div>
            <div>Margin<br /><b>±{M.error_margin}°</b></div>
          </div>
        )}
        {M && <ul className="mt-2 list-disc pl-5 text-xs text-slate-400">{M.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      </Card>
      {id && <ExtensionVisual id={id} report={report} />}
      {id && <ManualElbow key={JSON.stringify(M?.inputs || [])} id={id} report={report} onReport={onReport} />}
      <Card title="Automatic elbow extension screening (ICC 15° reference)">
        <div className="mb-3"><LegalityBadge c={L.classification} /></div>
        <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-6">
          <div>Arm horizontal<br /><b>{num(L.angle_at_horizontal)}</b> <span className="text-slate-500">#{L.horizontal_frame ?? '—'}</span></div>
          <div>Min elbow angle<br /><b>{num(L.min_angle)}</b></div>
          <div>At release<br /><b>{num(L.angle_at_br)}</b> <span className="text-slate-500">#{L.br_frame ?? '—'}</span></div>
          <div>Net extension Δθ<br /><b>{num(L.net_extension)}</b></div>
          <div>2D error margin<br /><b>{L.error_margin == null ? '—' : `±${L.error_margin}°`}</b></div>
          <div>Reference<br /><b>{L.threshold}°</b></div>
        </div>
        <p className="mt-2 text-xs text-slate-500">Δθ = θ(release) − min θ(arm horizontal → release). Elbow angle 180° = fully straight.
          Rule: Δθ &lt; 15° → <b className="text-emerald-400">Legal</b>; Δθ ≥ 15° → <b className="text-rose-400">Illegal</b>. Margin shown for information only.</p>
      </Card>
      <Card title="Elbow angle timeline (bowling arm)">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data} margin={{ left: -10, right: 10 }}>
            <CartesianGrid stroke="#1e293b" />
            <XAxis dataKey="frame" stroke="#94a3b8" fontSize={11} />
            <YAxis domain={[40, 190]} stroke="#94a3b8" fontSize={11} />
            <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} formatter={(v) => (v == null ? 'low confidence' : `${v}°`)} labelFormatter={(f) => `frame ${f}`} />
            {L.horizontal_frame != null && L.br_frame != null && <ReferenceArea x1={L.horizontal_frame} x2={L.br_frame} fill="#f59e0b" fillOpacity={0.12} />}
            {ffc != null && <ReferenceLine x={ffc} stroke="#a78bfa" label={{ value: 'FFC', fill: '#a78bfa', fontSize: 11 }} />}
            {L.horizontal_frame != null && <ReferenceLine x={L.horizontal_frame} stroke="#f59e0b" label={{ value: 'Arm horiz.', fill: '#f59e0b', fontSize: 11 }} />}
            {L.br_frame != null && <ReferenceLine x={L.br_frame} stroke="#f43f5e" label={{ value: 'BR', fill: '#f43f5e', fontSize: 11 }} />}
            <Line dataKey="angle" stroke="#38bdf8" dot={false} connectNulls={false} isAnimationActive={false} name="automatic" />
            <Line dataKey="manual" stroke="#e879f9" strokeWidth={0} dot={{ r: 5, fill: '#e879f9' }} isAnimationActive={false} name="manual" />
          </LineChart>
        </ResponsiveContainer>
        <p className="text-xs text-slate-500">Gaps = frames where the arm landmarks were below 0.5 confidence (not interpolated into the result).</p>
      </Card>
      {L.notes.length > 0 && <Card title="Measurement notes"><ul className="list-disc pl-5 text-sm text-slate-300">{L.notes.map((n) => <li key={n}>{n}</li>)}</ul></Card>}
    </div>
  )
}

const LEVEL = { 'Low concern': 0, 'Moderate concern': 1, 'High concern': 2, Unavailable: -1 }
const LEVEL_FILL = { 2: '#e11d48', 1: '#f59e0b', 0: '#10b981', '-1': '#475569' }
const LEVEL_TXT = { 2: 'text-rose-400', 1: 'text-amber-400', 0: 'text-emerald-400', '-1': 'text-slate-500' }
const REGION_LABEL = { lower_back: 'Lower back', shoulder: 'Shoulder', elbow: 'Elbow', front_knee: 'Front knee', ankle: 'Ankle', hip: 'Hip' }

function BodyMap({ worst, arm }) {
  const r = arm === 'right' ? -1 : 1      // bowling-side on viewer's left for a right-armer (facing viewer)
  const P = { shoulder: [100 + 28 * r, 70], elbow: [100 + 42 * r, 108], lower_back: [100, 128], hip: [100 - 18 * r, 150], front_knee: [100 - 16 * r, 200], ankle: [100 - 16 * r, 248] }
  return (
    <svg viewBox="0 0 200 270" className="mx-auto h-72">
      <g stroke="#475569" strokeWidth="6" strokeLinecap="round" fill="none">
        <circle cx="100" cy="35" r="16" />
        <line x1="100" y1="52" x2="100" y2="145" /><line x1="72" y1="70" x2="128" y2="70" />
        <line x1="72" y1="70" x2="58" y2="108" /><line x1="58" y1="108" x2="52" y2="140" />
        <line x1="128" y1="70" x2="142" y2="108" /><line x1="142" y1="108" x2="148" y2="140" />
        <line x1="82" y1="148" x2="118" y2="148" />
        <line x1="84" y1="150" x2="84" y2="200" /><line x1="84" y1="200" x2="84" y2="250" />
        <line x1="116" y1="150" x2="116" y2="200" /><line x1="116" y1="200" x2="116" y2="250" />
      </g>
      {Object.entries(P).map(([k, [x, y]]) => (
        <g key={k}><circle cx={x} cy={y} r="11" fill={LEVEL_FILL[worst[k] ?? -1]} opacity="0.9" />
          <title>{REGION_LABEL[k]}</title></g>
      ))}
    </svg>
  )
}

export function Injury({ report }) {
  const I = report.injury
  const worst = {}
  for (const f of I.flags) worst[f.region] = Math.max(worst[f.region] ?? -1, LEVEL[f.level])
  return (
    <div className="space-y-4">
      <Disclaimer>{I.disclaimer}</Disclaimer>
      <div className="grid gap-4 md:grid-cols-[260px_1fr]">
        <Card title="Body map (worst flag per region)">
          <BodyMap worst={worst} arm={report.bowling_arm} />
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {[[0, 'Low'], [1, 'Moderate'], [2, 'High'], [-1, 'Unavailable']].map(([l, t]) => (
              <span key={t} className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full" style={{ background: LEVEL_FILL[l] }} />{t}</span>
            ))}
          </div>
        </Card>
        <Card title="Screening flags (exact triggering measurements)">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500"><tr><th>Region</th><th>Trigger</th><th>Measured</th><th>Moderate / High</th><th>Level</th></tr></thead>
            <tbody>
              {I.flags.map((f) => (
                <tr key={f.trigger_metric} className="border-t border-slate-800 align-top" title={f.explanation}>
                  <td className="py-1.5 pr-2">{REGION_LABEL[f.region]}</td>
                  <td className="pr-2">{f.trigger_metric}<div className="text-xs text-slate-500">{f.explanation}</div></td>
                  <td className="font-mono">{f.measured == null ? '—' : `${f.measured}${f.unit === 'deg_s' ? '°/s' : '°'}`}</td>
                  <td className="font-mono text-xs text-slate-400">{f.threshold_moderate} / {f.threshold_high}</td>
                  <td className={LEVEL_TXT[LEVEL[f.level]]}>{f.level}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  )
}
