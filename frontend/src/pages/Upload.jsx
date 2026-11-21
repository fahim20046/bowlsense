import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Card } from '../components/ui'

export default function Upload({ onDone }) {
  const [file, setFile] = useState(null)
  const [arm, setArm] = useState('right')
  const [persp, setPersp] = useState('side_on')
  const [name, setName] = useState('')
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState(null)
  const [hint, setHint] = useState(null)   // {frame, x, y} normalized
  const pv = useRef(null)

  useEffect(() => {
    if (!file) return
    const u = URL.createObjectURL(file); setPreview(u); setHint(null)
    return () => URL.revokeObjectURL(u)
  }, [file])

  const clickBowler = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    setHint({ t: pv.current.currentTime,
      x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height })
  }

  useEffect(() => {
    if (!job || job.status === 'done' || job.status === 'failed') return
    const t = setTimeout(async () => {
      try {
        const s = await api.status(job.session_id)
        setJob(s)
        if (s.status === 'done') onDone(s.session_id)
        if (s.status === 'failed') setError(s.error)
      } catch (e) { setError(e.message) }
    }, 1000)
    return () => clearTimeout(t)
  }, [job, onDone])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    const f = new FormData()
    f.append('file', file); f.append('bowling_arm', arm); f.append('perspective', persp)
    if (name) f.append('bowler_name', name)
    if (hint) { f.append('hint_time', hint.t); f.append('hint_x', hint.x); f.append('hint_y', hint.y) }
    try { setJob({ ...(await api.upload(f)), progress: 0 }) } catch (err) { setError(err.message) }
  }

  const sel = 'w-full rounded bg-slate-800 p-2'
  return (
    <Card title="Upload delivery" className="mx-auto max-w-lg">
      <form onSubmit={submit} className="space-y-3">
        <input type="file" accept=".mp4,.mov,.avi" onChange={(e) => setFile(e.target.files[0])} className={sel} required />
        <div className="grid grid-cols-2 gap-3">
          <label>Bowling arm<select value={arm} onChange={(e) => setArm(e.target.value)} className={sel}>
            <option value="right">Right</option><option value="left">Left</option></select></label>
          <label>Camera view<select value={persp} onChange={(e) => setPersp(e.target.value)} className={sel}>
            <option value="side_on">Side-on</option><option value="front_on">Front-on</option><option value="rear">Rear</option></select></label>
        </div>
        {preview && (
          <div>
            <p className="mb-1 text-xs text-slate-400">Optional (recommended if other people are in frame): pause where the bowler is clearly separated from others, then click on the bowler.</p>
            <div className="relative">
              <video ref={pv} src={preview} controls muted className="w-full rounded" />
              <div onClick={clickBowler} className="absolute inset-x-0 top-0 bottom-10 cursor-crosshair" />
              {hint && <div className="pointer-events-none absolute h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-fuchsia-400"
                            style={{ left: `${hint.x * 100}%`, top: `${hint.y * 100}%` }} />}
            </div>
            <p className="text-xs text-fuchsia-300">{hint ? `Bowler marked at ${hint.t.toFixed(2)}s` : 'No bowler marked (auto-select)'}</p>
          </div>
        )}
        <input placeholder="Bowler name (optional, for history)" value={name} onChange={(e) => setName(e.target.value)} className={sel} />
        <button disabled={!file || (job && job.status !== 'failed')} className="w-full rounded bg-emerald-600 p-2 font-semibold disabled:opacity-40">Analyse</button>
      </form>
      {job && job.status !== 'failed' && (
        <div className="mt-4">
          <div className="mb-1 text-sm text-slate-400">{job.stage || job.status}… {Math.round((job.progress || 0) * 100)}%</div>
          <div className="h-2 rounded bg-slate-800"><div className="h-2 rounded bg-emerald-500" style={{ width: `${(job.progress || 0) * 100}%` }} /></div>
        </div>
      )}
      {error && <p className="mt-3 text-sm text-rose-400">Error: {error}</p>}
      <p className="mt-4 text-xs text-slate-500">Tip: static camera, full body in frame, ≥ 60 fps for best results.</p>
    </Card>
  )
}
