import { useEffect, useRef } from 'react'

export const ARM_IDS = { right: [12, 14, 16], left: [11, 13, 15] }

export const elbowAngle = (S, E, W) => {
  const a = [S[0] - E[0], S[1] - E[1]], b = [W[0] - E[0], W[1] - E[1]]
  const c = (a[0] * b[0] + a[1] * b[1]) / (Math.hypot(...a) * Math.hypot(...b))
  return (Math.acos(Math.max(-1, Math.min(1, c))) * 180) / Math.PI
}

/**
 * "Virtual" skeleton on a clean background (no video), fitted to the canvas.
 * The bowling arm is highlighted; the elbow gets an angle arc, the value, and a dashed
 * straight-arm reference (upper-arm direction extended) so the bend is easy to see.
 * Props: lm (33×[x,y,vis], image px, -1 = missing), connections, arm ('right'|'left'),
 *        armOverride ([S,E,W] manual clicks), size, title, sub, accent.
 */
export default function VirtualSkeleton({ lm, connections, arm = 'right', armOverride = null, size = 240, title, sub, accent = '#38bdf8' }) {
  const ref = useRef(null)
  const [si, ei, wi] = ARM_IDS[arm]

  useEffect(() => {
    const c = ref.current
    if (!c) return
    const dpr = window.devicePixelRatio || 1
    c.width = size * dpr; c.height = size * dpr
    const ctx = c.getContext('2d'); ctx.scale(dpr, dpr)
    // background grid
    ctx.fillStyle = '#0b1220'; ctx.fillRect(0, 0, size, size)
    ctx.strokeStyle = 'rgba(148,163,184,0.07)'; ctx.lineWidth = 1
    for (let g = 0; g <= size; g += size / 8) { ctx.beginPath(); ctx.moveTo(g, 0); ctx.lineTo(g, size); ctx.moveTo(0, g); ctx.lineTo(size, g); ctx.stroke() }

    const pts = lm ? lm.map((p) => (p && p[0] >= 0 && p[2] >= 0.3 ? [p[0], p[1]] : null)) : []
    const armPts = armOverride || (pts.length ? [pts[si], pts[ei], pts[wi]] : [null, null, null])
    const all = [...pts.filter(Boolean), ...armPts.filter(Boolean)]
    if (all.length < 3) {
      ctx.fillStyle = '#64748b'; ctx.font = '12px Inter, sans-serif'; ctx.textAlign = 'center'
      ctx.fillText('Bowler not tracked on this frame', size / 2, size / 2); return
    }
    // fit bounding box (square, padded)
    const xs = all.map((p) => p[0]), ys = all.map((p) => p[1])
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 1) * 1.25
    const T = (p) => [size / 2 + ((p[0] - cx) / span) * size, size / 2 + ((p[1] - cy) / span) * size]

    // body
    ctx.lineCap = 'round'; ctx.strokeStyle = 'rgba(203,213,225,0.55)'; ctx.lineWidth = 3
    for (const [a, b] of connections || []) {
      if ([si, ei, wi].includes(a) && [si, ei, wi].includes(b)) continue
      if (!pts[a] || !pts[b]) continue
      const A = T(pts[a]), B = T(pts[b]); ctx.beginPath(); ctx.moveTo(...A); ctx.lineTo(...B); ctx.stroke()
    }
    if (pts[0]) { const h = T(pts[0]); ctx.fillStyle = 'rgba(203,213,225,0.55)'; ctx.beginPath(); ctx.arc(h[0], h[1], size * 0.03, 0, 7); ctx.fill() }

    const [S, E, W] = armPts
    if (!(S && E && W)) return
    const s = T(S), e = T(E), w = T(W)
    // straight-arm reference: upper-arm direction extended past the elbow, forearm length
    const ux = e[0] - s[0], uy = e[1] - s[1], ul = Math.hypot(ux, uy) || 1
    const fl = Math.hypot(w[0] - e[0], w[1] - e[1])
    const ref2 = [e[0] + (ux / ul) * fl, e[1] + (uy / ul) * fl]
    ctx.setLineDash([5, 5]); ctx.strokeStyle = 'rgba(148,163,184,0.7)'; ctx.lineWidth = 2
    ctx.beginPath(); ctx.moveTo(...e); ctx.lineTo(...ref2); ctx.stroke(); ctx.setLineDash([])
    // bowling arm
    ctx.strokeStyle = accent; ctx.lineWidth = 6
    ctx.beginPath(); ctx.moveTo(...s); ctx.lineTo(...e); ctx.lineTo(...w); ctx.stroke()
    // bend arc between straight reference and forearm (= 180° − elbow angle)
    const a1 = Math.atan2(ref2[1] - e[1], ref2[0] - e[0]), a2 = Math.atan2(w[1] - e[1], w[0] - e[0])
    let d = a2 - a1; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI
    ctx.fillStyle = 'rgba(244,114,182,0.25)'; ctx.beginPath(); ctx.moveTo(...e); ctx.arc(e[0], e[1], size * 0.12, a1, a1 + d, d < 0); ctx.closePath(); ctx.fill()
    for (const [p, col] of [[s, '#f472b6'], [e, '#facc15'], [w, '#38bdf8']]) { ctx.fillStyle = col; ctx.beginPath(); ctx.arc(p[0], p[1], 5, 0, 7); ctx.fill() }
    // label
    const ang = elbowAngle(S, E, W)
    const tx = Math.min(size - 70, Math.max(4, e[0] + 10)), ty = Math.min(size - 8, Math.max(20, e[1] - 12))
    ctx.fillStyle = 'rgba(2,6,23,0.85)'; ctx.fillRect(tx - 4, ty - 15, 74, 20)
    ctx.fillStyle = '#fde68a'; ctx.font = 'bold 13px "JetBrains Mono", monospace'; ctx.textAlign = 'left'
    ctx.fillText(`${ang.toFixed(1)}°`, tx, ty)
  }, [lm, connections, arm, armOverride, size, accent, si, ei, wi])

  return (
    <div className="text-center">
      {title && <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">{title}</div>}
      <canvas ref={ref} style={{ width: size, height: size }} className="mx-auto rounded-xl border border-slate-700/60" />
      {sub && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
    </div>
  )
}
