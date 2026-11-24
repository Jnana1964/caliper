import React, { useEffect, useState } from 'react'

const WORD = 'Caliper'

/**
 * Title screen. Shows the project name alone, animates it in, and hands off to
 * the app on a single click (or Enter / Space). The exit is a deliberate
 * transition rather than a cut, so the name reads as a title card.
 */
export default function Splash({ onEnter }) {
  const [leaving, setLeaving] = useState(false)

  function go() {
    if (leaving) return
    setLeaving(true)
    setTimeout(onEnter, 620)
  }

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        go()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <div
      onClick={go}
      role="button"
      tabIndex={0}
      aria-label="Enter Caliper"
      className={`splash fixed inset-0 z-50 flex cursor-pointer select-none flex-col items-center justify-center overflow-hidden px-6 ${
        leaving ? 'is-leaving' : ''
      }`}
    >
      <div className="splash-glow" aria-hidden="true" />

      <div className="splash-stage flex flex-col items-center">
        <span className="splash-eyebrow label">an evidence gated document agent</span>

        <h1 className="splash-word mt-5 flex items-end font-semibold tracking-[-0.04em] text-mist-100">
          {WORD.split('').map((ch, i) => (
            <span key={i} className="splash-ch" style={{ '--i': i }}>
              {ch}
            </span>
          ))}
          <span className="splash-ch splash-dot text-acc" style={{ '--i': WORD.length }}>
            .
          </span>
        </h1>

        <div className="splash-rule mt-6" aria-hidden="true" />

        <p className="splash-sub mt-6 max-w-md text-center text-[13.5px] leading-relaxed text-mist-500">
          Answers only what the documents support. Cites every claim. Refuses the rest.
        </p>

        <div className="splash-cta mt-10 flex flex-col items-center gap-3">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              go()
            }}
            className="btn-primary px-6"
          >
            Enter
          </button>
          <span className="label opacity-60">click anywhere to continue</span>
        </div>
      </div>
    </div>
  )
}