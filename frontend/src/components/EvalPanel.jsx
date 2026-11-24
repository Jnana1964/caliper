import React, { useEffect, useState } from 'react'
import { fmtMs, metrics } from '../lib/api'

function Row({ k, v, hint }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line/60 py-2 last:border-0">
      <span className="text-[13px] text-mist-300">{k}</span>
      <span className="font-mono text-[13px] text-mist-100">{v}</span>
      {hint && <span className="label shrink-0">{hint}</span>}
    </div>
  )
}

export default function EvalPanel() {
  const [m, setM] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    const load = () => metrics().then(setM).catch((e) => setErr(e.message))
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  if (err) return <div className="card p-5 text-[13px] text-bad">metrics unavailable: {err}</div>
  if (!m) return <div className="card p-5 text-[13px] text-mist-500">loading…</div>

  const lat = m.latency_ms || {}
  const cost = m.cost_usd || {}

  return (
    <div className="space-y-5">
      <div className="card p-5">
        <p className="label mb-3">live service metrics</p>
        {m.requests ? (
          <>
            <Row k="requests in window" v={m.requests} />
            <Row k="latency p50 / p95 / p99" v={`${fmtMs(lat.p50)} / ${fmtMs(lat.p95)} / ${fmtMs(lat.p99)}`} />
            <Row k="output tokens / sec" v={m.tokens?.output_tokens_per_sec ?? '—'} />
            <Row k="refusal rate" v={`${((m.refusal_rate ?? 0) * 100).toFixed(1)}%`} />
            <Row k="cost per request" v={cost.mean_per_request ?? cost.note ?? '—'} />
            <div className="mt-4">
              <p className="label mb-2">outcomes</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(m.outcomes || {}).map(([k, v]) => (
                  <span key={k} className="chip">{k}: {v}</span>
                ))}
              </div>
            </div>
            {m.node_latency_ms_p95 && (
              <div className="mt-4">
                <p className="label mb-2">p95 latency per node</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(m.node_latency_ms_p95).map(([k, v]) => (
                    <span key={k} className="chip">{k}: {fmtMs(v)}</span>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <p className="text-[13px] text-mist-500">No requests yet. Ask something first.</p>
        )}
      </div>

      <div className="card p-5">
        <p className="label mb-3">evaluation</p>
        <p className="text-[13px] leading-relaxed text-mist-300">
          The numbers that matter are not live metrics — they come from running a fixed question set
          where the answers are known in advance:
        </p>
        <pre className="mt-3 overflow-x-auto rounded-lg border border-line bg-ink-900/70 p-3 font-mono text-[11.5px] text-mist-300">
python eval/run_eval.py --compare</pre>
        <p className="mt-3 text-[13px] leading-relaxed text-mist-300">
          That runs the set twice — verification off, then on — and prints the difference in
          hallucination rate. Write your own{' '}
          <span className="font-mono text-mist-100">eval/questions.yaml</span>, and make a third of
          it questions the documents genuinely cannot answer. Those are what reveal whether the
          system guesses.
        </p>
        <p className="mt-3 text-[12px] italic leading-relaxed text-mist-500">
          Results are deliberately not hardcoded here. Paste your measured numbers into the README
          once you have run it against a real corpus — an empty table costs nothing, an invented one
          costs the interview.
        </p>
      </div>
    </div>
  )
}
