import { PHASE_LABEL } from '../api'
import { Card, MetricTable } from '../components/ui'

export default function Report({ report }) {
  const b = report.biomechanics
  const cols = Object.keys(Object.values(b.phase_table)[0] || {})
  return (
    <div className="space-y-4">
      <Card title="Upper body"><MetricTable metrics={b.upper_body} /></Card>
      <Card title="Lower body"><MetricTable metrics={b.lower_body} /></Card>
      <Card title="Overall posture & balance"><MetricTable metrics={b.posture} /></Card>
      <Card title="Phase-by-phase joint angles (°, ratios for height/offset)">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr><th className="text-left">Phase</th>{cols.map((c) => <th key={c} className="px-1">{c.replace(/_/g, ' ')}</th>)}</tr></thead>
            <tbody>
              {Object.entries(b.phase_table).map(([p, row]) => (
                <tr key={p} className="border-t border-slate-800">
                  <td className="py-1 pr-2">{PHASE_LABEL[p]}</td>
                  {cols.map((c) => <td key={c} className="px-1 text-center font-mono">{row[c] == null ? '—' : row[c].toFixed(1)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
