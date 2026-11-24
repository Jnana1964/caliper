import React from 'react'

export default function Sidebar({ health, docs, mode, setMode, view, setView }) {
  const ready = health?.ready
  return (
    <aside className="flex w-full shrink-0 flex-col gap-5 border-b border-line bg-ink-800/40 p-5 lg:h-screen lg:w-72 lg:border-b-0 lg:border-r">
      <div>
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-acc/35 bg-acc/10">
            <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] text-acc" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2.6" y="8.4" width="18.8" height="7.2" rx="1.6" />
              <path d="M7 8.4v3M11 8.4v4.4M15 8.4v3M19 8.4v4.4" />
            </svg>
          </span>
          <h1 className="font-semibold uppercase leading-none tracking-[0.22em] text-[17px] text-mist-100">
            Caliper<span className="text-acc">.</span>
          </h1>
        </div>
        <div className="mt-3 h-px w-full bg-gradient-to-r from-acc/60 via-line to-transparent" />
        <p className="mt-2.5 text-[12px] leading-snug text-mist-500">
          A tool-using agent that answers from your documents — and refuses when they don't.
        </p>
      </div>

      <div className="flex gap-1 rounded-lg border border-line bg-ink-900/60 p-1">
        {['ask', 'evaluation'].map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`flex-1 rounded-md px-2 py-1.5 text-[12px] font-medium capitalize transition ${
              view === v ? 'bg-ink-600 text-mist-100' : 'text-mist-500 hover:text-mist-300'
            }`}
          >
            {v}
          </button>
        ))}
      </div>

      <div>
        <p className="label mb-2">reasoning mode</p>
        <div className="space-y-1.5">
          {[
            { id: 'agent', t: 'Agent', d: 'The model picks its own tools each turn.' },
            { id: 'linear', t: 'Pipeline', d: 'Fixed retrieve → grade → verify path.' },
          ].map((m) => (
            <button
              key={m.id}
              onClick={() => setMode(m.id)}
              className={`w-full rounded-lg border p-2.5 text-left transition ${
                mode === m.id
                  ? 'border-acc/50 bg-acc/5'
                  : 'border-line hover:border-mist-500/50'
              }`}
            >
              <span className={`text-[13px] font-medium ${mode === m.id ? 'text-acc' : 'text-mist-100'}`}>
                {m.t}
              </span>
              <span className="mt-0.5 block text-[11px] leading-snug text-mist-500">{m.d}</span>
            </button>
          ))}
        </div>
        <p className="mt-2 text-[11px] leading-snug text-mist-500">
          Both run on the same corpus so you can compare them honestly.
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="label mb-2">corpus</p>
        {docs?.documents?.length ? (
          <ul className="space-y-1">
            {docs.documents.map((d) => (
              <li key={d.source} className="flex items-baseline justify-between gap-2 text-[12px]">
                <span className="truncate text-mist-300" title={d.source}>{d.source}</span>
                <span className="label shrink-0">{d.chunks}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[12px] leading-snug text-mist-500">
            Nothing indexed. Run{' '}
            <span className="font-mono text-mist-300">python -m app.ingest docs/</span>. Until then
            every question is refused — correctly.
          </p>
        )}
      </div>

      <div className="border-t border-line pt-3">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${ready ? 'bg-acc' : 'bg-warn'}`} />
          <span className="text-[12px] text-mist-300">{ready ? 'ready' : 'no documents'}</span>
        </div>
        <p className="mt-1 font-mono text-[10.5px] text-mist-500">
          {health?.model || '—'} · {docs?.total_chunks ?? 0} chunks
          {health?.offline_mode ? ' · offline stub' : ''}
        </p>
        <p className="mt-2 text-[10.5px] leading-snug text-mist-500">
          Independent project. Not an official government service. Verify everything on the official
          portal before acting on it.
        </p>
      </div>
    </aside>
  )
}