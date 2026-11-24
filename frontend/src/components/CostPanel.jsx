import React from 'react'
import { fmtCost, fmtMs } from '../lib/api'

function Stat({ label, value, hint, tone = '' }) {
  return (
    <div className="min-w-0">
      <p className="label">{label}</p>
      <p className={`truncate font-mono text-[15px] ${tone || 'text-mist-100'}`}>{value}</p>
      {hint && <p className="mt-0.5 truncate text-[11px] text-mist-500">{hint}</p>}
    </div>
  )
}

export default function CostPanel({ result }) {
  if (!result) return null
  const u = result.usage || {}
  const unconfigured = u.cost_usd == null

  return (
    <div className="card p-5">
      <p className="label mb-3">what this answer cost</p>

      <div className="grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-4">
        <Stat label="latency" value={fmtMs(result.latency_ms)} />
        <Stat
          label="cost"
          value={fmtCost(u.cost_usd)}
          tone={unconfigured ? 'text-warn text-[13px]' : ''}
          hint={unconfigured ? 'see config/pricing.yaml' : null}
        />
        <Stat label="tokens" value={`${u.tokens_in ?? 0} → ${u.tokens_out ?? 0}`} hint="in → out" />
        <Stat label="model calls" value={u.llm_calls ?? 0} hint={`${result.steps?.length ?? 0} tool calls`} />
      </div>

      {unconfigured && (
        <p className="mt-4 border-t border-line pt-3 text-[12px] leading-relaxed text-mist-500">
          Cost reads <span className="font-mono text-warn">unconfigured</span> rather than
          <span className="font-mono"> $0.00</span> on purpose. Token prices change, and a figure
          whose provenance nobody recorded is worse than none. Fill in{' '}
          <span className="font-mono text-mist-300">config/pricing.yaml</span> from the official
          page and set <span className="font-mono text-mist-300">verified: true</span>.
        </p>
      )}

      {result.tools_used?.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="label mb-2">tools the agent chose</p>
          <div className="flex flex-wrap gap-1.5">
            {result.tools_used.map((t, i) => (
              <span key={i} className="chip">
                {i + 1}. {t}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
