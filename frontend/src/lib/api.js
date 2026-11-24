const BASE = import.meta.env.VITE_API_BASE || '/api'

export async function getJSON(path) {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`${path} -> ${r.status}`)
  return r.json()
}

export const health = () => getJSON('/healthz')
export const metrics = () => getJSON('/metrics')
export const documents = () => getJSON('/documents')

export async function ask(question, mode) {
  const r = await fetch(`${BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, mode, trace: true }),
  })
  const body = await r.json()
  if (!r.ok) throw new Error(body.detail || `ask -> ${r.status}`)
  return body
}

/**
 * Stream an answer.
 *
 * EventSource only does GET, and the question belongs in a POST body, so the
 * SSE frames are parsed by hand off the fetch body stream. Frames are split on
 * a blank line; a partial frame is held in `buffer` until the rest arrives.
 */
export async function askStream(question, mode, onEvent, signal) {
  const res = await fetch(`${BASE}/ask/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, mode, trace: true }),
    signal,
  })
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `stream -> ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let split
    while ((split = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, split)
      buffer = buffer.slice(split + 2)

      let event = 'message'
      const dataLines = []
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
      }
      if (!dataLines.length) continue
      try {
        onEvent(event, JSON.parse(dataLines.join('\n')))
      } catch {
        onEvent(event, { raw: dataLines.join('\n') })
      }
    }
  }
}

export const fmtMs = (ms) =>
  ms == null ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`

export const fmtCost = (usd) =>
  usd == null ? 'unconfigured' : usd < 0.01 ? `$${usd.toFixed(5)}` : `$${usd.toFixed(4)}`
