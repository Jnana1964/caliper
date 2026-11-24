import React from 'react'

const OUTCOME = {
  answered: { tone: 'acc', title: 'Answered', note: 'Every claim below was checked against the cited sources.' },
  refused_out_of_scope: { tone: 'warn', title: 'Out of scope', note: 'The question is not about the ingested documents.' },
  refused_no_evidence: { tone: 'warn', title: 'Refused — no evidence', note: 'Nothing in the documents answers this.' },
  refused_ungrounded: { tone: 'bad', title: 'Refused — unsupported', note: 'A draft existed but failed verification, so it was withheld.' },
}

const TONE = {
  acc: 'border-acc/40 bg-acc/5',
  warn: 'border-warn/40 bg-warn/5',
  bad: 'border-bad/40 bg-bad/5',
}
const DOT = { acc: 'bg-acc', warn: 'bg-warn', bad: 'bg-bad' }

/** Render [S1] markers as clickable chips tied to the citation list. */
function withCitations(text, citations, onCite) {
  const parts = String(text).split(/(\[S\d+\])/g)
  return parts.map((part, i) => {
    const m = part.match(/^\[S(\d+)\]$/)
    if (!m) return <span key={i}>{part}</span>
    const cite = citations[Number(m[1]) - 1]
    return (
      <button
        key={i}
        onClick={() => cite && onCite(cite)}
        title={cite ? `${cite.source}${cite.page ? ` · page ${cite.page}` : ''}` : 'unknown source'}
        className="mx-0.5 rounded border border-acc/40 bg-acc/10 px-1 font-mono text-[11px] text-acc hover:bg-acc/20"
      >
        S{m[1]}
      </button>
    )
  })
}

export default function AnswerCard({ result, draft, onCite }) {
  const text = result?.answer ?? draft?.answer
  if (!text) return null

  const citations = result?.citations ?? draft?.citations ?? []
  const meta = OUTCOME[result?.outcome] || { tone: 'acc', title: 'Drafting…', note: 'Not yet verified.' }

  return (
    <div className={`card animate-rise border p-5 ${TONE[meta.tone]}`}>
      <div className="mb-3 flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${DOT[meta.tone]}`} />
        <span className="text-sm font-semibold">{meta.title}</span>
        {result?.grounded === true && <span className="chip text-acc border-acc/30">verified</span>}
        {result?.grounded === false && <span className="chip text-bad border-bad/40">unsupported</span>}
      </div>

      <p className="whitespace-pre-wrap text-[14.5px] leading-[1.7] text-mist-100">
        {withCitations(text, citations, onCite)}
      </p>

      <p className="mt-3 text-[12px] italic text-mist-500">{meta.note}</p>

      {citations.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="label mb-2">sources</p>
          <ul className="space-y-1">
            {citations.map((c) => (
              <li key={c.chunk_id} className="flex items-center gap-2 text-[12.5px] text-mist-300">
                <span className="chip text-acc border-acc/30">{c.marker}</span>
                <span className="truncate">{c.source}</span>
                {c.page != null && <span className="label">page {c.page}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
