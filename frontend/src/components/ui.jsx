import { STATUS_LABEL } from '../api'
import { metricInfo, rangeStatus, rangeText } from '../metricInfo'

export const Card = ({ title, children, className = '', right = null }) => (
  <div className={`card rounded-md p-5 ${className}`}>
    {title && (
      <div className="mb-4 flex items-center gap-2 border-b border-dashed border-slate-700 pb-2">
        <Seam />
        <h3 className="font-display text-lg font-bold uppercase tracking-wide text-slate-100">{title}</h3>
        {right && <div className="ml-auto">{right}</div>}
      </div>
    )}
    {children}
  </div>
)

/** Small cricket-ball mark with its stitched seam. */
export const Seam = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true">
    <circle cx="10" cy="10" r="9" fill="#b3261e" />
    <path d="M6 2.8 C9 7 9 13 6 17.2 M14 2.8 C11 7 11 13 14 17.2" stroke="#fff6e8" strokeWidth="1.2" fill="none" strokeDasharray="1.6 1.4" />
  </svg>
)

/** Circular score gauge (0–100). */
export const Gauge = ({ value, size = 120, label = '' }) => {
  const r = size / 2 - 10, c = 2 * Math.PI * r
  const v = value == null ? 0 : Math.max(0, Math.min(100, value))
  const color = value == null ? '#a29f97' : v >= 75 ? '#2f7d3c' : v >= 50 ? '#c98a12' : '#b3261e'
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#e7e0d0" strokeWidth="10" fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth="10" fill="none" strokeLinecap="round"
                strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)} style={{ transition: 'stroke-dashoffset .8s' }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="text-3xl font-extrabold tracking-tight">{value == null ? '—' : Math.round(value)}</div>
          {label && <div className="text-[10px] uppercase tracking-wider text-slate-400">{label}</div>}
        </div>
      </div>
    </div>
  )
}

/** KPI tile: small label, big value, optional sub-line. */
export const Kpi = ({ label, children, sub, accent = 'from-emerald-500/20' }) => (
  <div className="card relative overflow-hidden rounded-md p-4">
    <div className="absolute inset-x-0 top-0 h-1.5 bg-[var(--color-ball)]" />
    <div className="mt-1 font-display text-sm font-bold uppercase tracking-wider text-slate-400">{label}</div>
    <div className="mt-2">{children}</div>
    {sub && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
  </div>
)

const REL_COLOR = { high: 'bg-emerald-900 text-emerald-300', reduced: 'bg-amber-900 text-amber-300', low: 'bg-rose-900 text-rose-300' }
export const Reliability = ({ r }) => (
  <span className={`rounded px-1.5 py-0.5 text-xs ${REL_COLOR[r]}`}>{r}</span>
)

const UNIT = { deg: '°', ratio: '', pct_height: '% ht', height_per_s: ' ht/s', height_per_s2: ' ht/s²', deg_s: '°/s', km_h: ' km/h' }
export const fmt = (v, unit) => (v === null || v === undefined ? '—' : `${v.toFixed(unit === 'ratio' ? 2 : 1)}${UNIT[unit] ?? ''}`)

export const MetricValue = ({ m }) =>
  m.status === 'ok'
    ? <span className="font-mono">{fmt(m.value, m.unit)}</span>
    : <span className="text-xs italic text-slate-500">{STATUS_LABEL[m.status] || 'Unavailable'}</span>

export const MetricTable = ({ metrics }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-sm">
      <thead className="text-left text-xs text-slate-500">
        <tr><th className="py-1">Metric</th><th>Value</th><th>Typical range</th><th>Frame</th><th>Conf.</th><th>View reliability</th></tr>
      </thead>
      <tbody>
        {metrics.map((m) => {
          const info = metricInfo(m.key)
          const st = m.status === 'ok' ? rangeStatus(info, m.value) : null
          return (
            <tr key={m.key + m.label} className="border-t border-slate-800 align-top">
              <td className="py-2 pr-3">
                <div className="font-medium text-slate-200">{m.label}</div>
                {info && <div className="mt-0.5 max-w-md text-xs leading-snug text-slate-400">{info.d}</div>}
              </td>
              <td className="whitespace-nowrap py-2 pr-2">
                <MetricValue m={m} />
                {st && <span className={`ml-2 rounded px-1.5 py-0.5 text-[10px] font-semibold ${st === 'in' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'}`}>{st === 'in' ? 'in range' : 'outside'}</span>}
              </td>
              <td className="whitespace-nowrap py-2 pr-2 font-mono text-xs text-slate-400">{rangeText(info, m.unit)}</td>
              <td className="py-2 text-slate-400">{m.frame ?? '—'}</td>
              <td className={`py-2 ${m.confidence < 0.5 ? 'text-rose-400' : 'text-slate-300'}`}>{m.confidence.toFixed(2)}</td>
              <td className="py-2"><Reliability r={m.reliability} /></td>
            </tr>
          )
        })}
      </tbody>
    </table>
    <p className="mt-2 text-[11px] text-slate-500">Typical ranges are coaching guidance for a well-coordinated delivery (approximate, 2D video), not medical norms. "Low" view reliability = not measured well from this camera angle.</p>
  </div>
)
