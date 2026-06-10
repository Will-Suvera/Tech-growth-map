import { useState, useRef, useMemo, useEffect, useCallback, useId } from 'react'

const MAX_RESULTS = 8

// Rank practices against a query matched on ODS code, name or postcode.
// Lower score = better match; exported for unit testing.
export function searchPractices(practices, rawQuery, limit = MAX_RESULTS) {
  const q = (rawQuery || '').trim().toUpperCase()
  if (!q) return []
  const qNoSpace = q.replace(/\s+/g, '')

  const scored = []
  for (const p of practices || []) {
    const ods = (p.ods || '').toUpperCase()
    const name = (p.name || '').toUpperCase()
    const postNoSpace = (p.postcode || '').toUpperCase().replace(/\s+/g, '')

    let score = Infinity
    if (ods === q) score = 0
    else if (postNoSpace && postNoSpace === qNoSpace) score = 1
    else if (ods.startsWith(q)) score = 2
    else if (name.startsWith(q)) score = 3
    else if (postNoSpace && postNoSpace.startsWith(qNoSpace)) score = 4
    else if (name.includes(q)) score = 5
    else if (ods.includes(q)) score = 6
    else if (postNoSpace && postNoSpace.includes(qNoSpace)) score = 7

    if (score !== Infinity) scored.push({ p, score })
  }

  scored.sort((a, b) => a.score - b.score || (a.p.name || '').localeCompare(b.p.name || ''))
  return scored.slice(0, limit).map(s => s.p)
}

export default function MapSearch({ practices, onSelect }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const containerRef = useRef(null)
  const inputRef = useRef(null)
  const buttonRef = useRef(null)
  const returnFocusRef = useRef(false)
  const listId = useId()

  const results = useMemo(() => searchPractices(practices, query), [practices, query])
  const showResults = query.trim().length > 0

  const close = useCallback((returnFocus = false) => {
    returnFocusRef.current = returnFocus
    setOpen(false)
    setQuery('')
    setActiveIdx(0)
  }, [])

  // Focus the input when opening; return focus to the trigger when closing
  // via keyboard/explicit action (WCAG 2.4.3), but not on outside-click.
  useEffect(() => {
    if (open) inputRef.current?.focus()
    else if (returnFocusRef.current) {
      returnFocusRef.current = false
      buttonRef.current?.focus()
    }
  }, [open])

  // Keep the active option scrolled into view during keyboard navigation.
  useEffect(() => {
    if (open) document.getElementById(`${listId}-opt-${activeIdx}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [activeIdx, open, listId])

  // Close when clicking anywhere outside the control.
  useEffect(() => {
    if (!open) return
    const onDown = e => {
      if (containerRef.current && !containerRef.current.contains(e.target)) close()
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open, close])

  function choose(practice) {
    if (!practice) return
    onSelect?.(practice)
    close(true)
  }

  function onKeyDown(e) {
    if (e.key === 'Escape') { close(true); return }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, results.length - 1)); return }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, 0)); return }
    if (e.key === 'Enter') { e.preventDefault(); choose(results[activeIdx]); return }
  }

  const Magnifier = (
    <svg className="map-search-icon" viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
      <circle cx="8.5" cy="8.5" r="5.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <line x1="12.6" y1="12.6" x2="17.5" y2="17.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )

  if (!open) {
    return (
      <div className="map-search" ref={containerRef}>
        <button
          ref={buttonRef}
          type="button"
          className="map-search-btn"
          onClick={() => setOpen(true)}
          aria-label="Search practices"
          title="Search by ODS code, name or postcode"
        >
          {Magnifier}
        </button>
      </div>
    )
  }

  return (
    <div className="map-search open" ref={containerRef}>
      <div className="map-search-bar">
        {Magnifier}
        <input
          ref={inputRef}
          className="map-search-input"
          type="text"
          role="combobox"
          aria-expanded={showResults}
          aria-controls={listId}
          aria-activedescendant={showResults && results[activeIdx] ? `${listId}-opt-${activeIdx}` : undefined}
          aria-autocomplete="list"
          value={query}
          placeholder="ODS code, practice name or postcode"
          onChange={e => { setQuery(e.target.value); setActiveIdx(0) }}
          onKeyDown={onKeyDown}
          aria-label="Search practices by ODS code, name or postcode"
          autoComplete="off"
          spellCheck="false"
        />
        <button type="button" className="map-search-close" onClick={() => close(true)} aria-label="Close search">×</button>
      </div>
      {showResults && (
        <ul className="map-search-results" id={listId} role="listbox">
          {results.length === 0 ? (
            <li className="map-search-empty">No matching practice</li>
          ) : (
            results.map((p, i) => (
              <li
                key={p.ods}
                id={`${listId}-opt-${i}`}
                role="option"
                aria-selected={i === activeIdx}
                className={`map-search-result${i === activeIdx ? ' active' : ''}`}
                onMouseEnter={() => setActiveIdx(i)}
                onMouseDown={e => { e.preventDefault(); choose(p) }}
              >
                <span className="map-search-result-name">{p.name}</span>
                <span className="map-search-result-meta">{p.ods}{p.postcode ? ` · ${p.postcode}` : ''}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}
