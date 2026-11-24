import React from 'react'
import { fmtMs } from '../lib/api'

const TOOL_META = {
  search_documents: { icon: '⌕', label: 'search documents' },
  lookup_number: { icon: '#', label: 'lookup figures' },
  calculate: { icon: '=', label: 'calculate' },
  current_date: { icon: '◷', label: 'current date' },
  finish: { icon: '✓', label: 'finish' },
}

function StepCard({ step, timing }) {
  const meta = TOOL_META[step.tool] || { icon: '•', label: step.tool }
  const failed = step.ok === false
  return (
    <li className="relative pl-9 pb-5 animate-rise">
      <span
        className={`absolute left-[9px] top-1.5 h-3 w-3 rounded-full border-2 ${
          failed ? 'border-bad bg-bad/30' : 'border-acc bg-acc/30'
        }`}
      />
      <div className="flex flex-wrap items-center gap-2">
        <span className="label">step {step.step}</span>
        <span className={`chip ${failed ? 'text-bad border-bad/40' : 'text-acc border-acc/30'}`}>
          <span aria-hidden>{meta.icon}</span>
          {meta.label}
        </span>
        {timing && <span className="label">{fmtMs(timing.ms)}</span>}
        {step.result_count > 0 && <span className="label">{step.result_count} hits</span>}
        {step.result != null && <span className="chip">= {String(step.result)}</span>}
      </div>

      {step.thought && (
        <p className="mt-1.5 text-[13px] leading-relaxed text-mist-300">{step.thought}</p>
      )}

      {step.args && Object.keys(step.args).length > 0 && (
        <pre className="mt-2 overflow-x-auto rounded-lg border border-line bg-ink-900/70 p-2.5 font-mono text-[11px] text-mist-500">
{JSON.stringify(step.args, null, 2)}
        </pre>
      )}

      {failed && <p className="mt-1.5 font-mono text-[11px] text-bad">{step.error}</p>}
    </li>
  )
}

export default function AgentTrace({ steps, timings, running, mode }) {
  if (mode === 'linear') {
    return (
      <div className="card p-5">
        <p className="label mb-2">pipeline mode</p>
        <p className="text-[13px] leading-relaxed text-mist-300">
          The fixed pipeline is running: route → retrieve → grade → generate → verify. No tool
          selection happens in this mode. Switch to <span className="text-acc">agent</span> to watch
          the model choose its own tools.
        </p>
      </div>
    )
  }

  if (!steps.length && !running) {
    return (
      <div className="card p-5">
        <p className="label mb-2">agent trace</p>
        <p className="text-[13px] leading-relaxed text-mist-500">
          Ask something. Each tool the agent decides to call appears here as it happens — what it
          chose, why, and what came back.
        </p>
      </div>
    )
  }

  const byNode = Object.fromEntries((timings || []).map((t) => [t.node, t]))

  return (
    <div className="card p-5">
      <div className="mb-4 flex items-center justify-between">
        <p className="label">agent trace</p>
        {running && (
          <span className="flex items-center gap-2 text-[11px] text-acc">
            <span className="h-2 w-2 animate-ring rounded-full bg-acc" />
            thinking
          </span>
        )}
      </div>

      <ol className="relative">
        <span className="absolute left-[14px] top-2 h-[calc(100%-1rem)] w-px bg-line" />
        {steps.map((s) => (
          <StepCard key={s.step} step={s} timing={byNode[`step${s.step}:${s.tool}`]} />
        ))}
        {running && (
          <li className="relative pl-9">
            <span className="absolute left-[9px] top-1.5 h-3 w-3 animate-ring rounded-full border-2 border-acc bg-acc/20" />
            <span className="label">deciding next tool…</span>
          </li>
        )}
      </ol>
    </div>
  )
}
