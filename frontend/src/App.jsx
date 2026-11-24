import React, { useCallback, useEffect, useRef, useState } from 'react'
import AgentTrace from './components/AgentTrace'
import AnswerCard from './components/AnswerCard'
import CostPanel from './components/CostPanel'
import EvalPanel from './components/EvalPanel'
import Sidebar from './components/Sidebar'
import Splash from './components/Splash'
import { askStream, documents, health } from './lib/api'

const SAMPLES = [
  'What is the benefit amount and how is it paid?',
  'Who is eligible, and what is the land or income limit?',
  'What documents do I need to apply?',
  'What is the appeal process if my application is rejected?',
]

export default function App() {
  const [entered, setEntered] = useState(false)
  const [view, setView] = useState('ask')
  const [mode, setMode] = useState('agent')
  const [q, setQ] = useState('')
  const [steps, setSteps] = useState([])
  const [draft, setDraft] = useState(null)
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [hz, setHz] = useState(null)
  const [docs, setDocs] = useState(null)
  const abortRef = useRef(null)

  const refresh = useCallback(() => {
    health().then(setHz).catch(() => setHz(null))
    documents().then(setDocs).catch(() => setDocs(null))
  }, [])

  useEffect(refresh, [refresh])

  async function submit(e) {
    e?.preventDefault()
    const question = q.trim()
    if (question.length < 3 || running) return

    setRunning(true)
    setError(null)
    setSteps([])
    setDraft(null)
    setResult(null)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      await askStream(
        question,
        mode,
        (event, data) => {
          if (event === 'step') setSteps((prev) => [...prev, data])
          else if (event === 'draft') setDraft(data)
          else if (event === 'done') setResult(data)
          else if (event === 'error') setError(data.error)
        },
        ctrl.signal
      )
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
    } finally {
      setRunning(false)
      abortRef.current = null
      refresh()
    }
  }

  function stop() {
    abortRef.current?.abort()
    setRunning(false)
  }

  if (!entered) return <Splash onEnter={() => setEntered(true)} />

  return (
    <div className="app-enter flex min-h-screen flex-col lg:flex-row">
      <Sidebar health={hz} docs={docs} mode={mode} setMode={setMode} view={view} setView={setView} />

      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8">
          {view === 'evaluation' ? (
            <EvalPanel />
          ) : (
            <>
              <header className="mb-7">
                <h2 className="text-[22px] font-semibold tracking-tight">Ask the documents</h2>
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-mist-500">
                  Every claim is cited. If the corpus doesn't support an answer, the agent refuses
                  instead of guessing — watch it decide below.
                </p>
              </header>

              <form onSubmit={submit} className="card mb-6 p-2">
                <textarea
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(e)
                  }}
                  rows={3}
                  placeholder="Ask a question about the ingested documents…"
                  className="w-full resize-none bg-transparent px-3 py-2.5 text-[14.5px] leading-relaxed outline-none placeholder:text-mist-500"
                />
                <div className="flex items-center justify-between gap-3 px-2 pb-1">
                  <span className="label hidden sm:block">⌘ / ctrl + enter to send</span>
                  <div className="flex gap-2">
                    {running && (
                      <button type="button" onClick={stop} className="btn-ghost">
                        Stop
                      </button>
                    )}
                    <button type="submit" disabled={running || q.trim().length < 3} className="btn-primary">
                      {running ? 'Working…' : 'Ask'}
                    </button>
                  </div>
                </div>
              </form>

              {!steps.length && !result && !running && (
                <div className="mb-6 flex flex-wrap gap-2">
                  {SAMPLES.map((s) => (
                    <button
                      key={s}
                      onClick={() => setQ(s)}
                      className="rounded-lg border border-line px-3 py-1.5 text-left text-[12.5px] text-mist-300 transition hover:border-acc/40 hover:text-mist-100"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}

              {error && (
                <div className="card mb-6 border-bad/40 bg-bad/5 p-4 text-[13px] text-bad">{error}</div>
              )}

              <div className="space-y-5">
                <AnswerCard
                  result={result}
                  draft={draft}
                  onCite={(c) => alert(`${c.source}${c.page ? ` · page ${c.page}` : ''}`)}
                />
                <AgentTrace steps={steps} timings={result?.timings} running={running} mode={mode} />
                <CostPanel result={result} />
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}