import { useMemo } from 'react'

export default function PracticeTicker({ practices, liveOds, fullPlannerOds, waitlistOds }) {
  const items = useMemo(() => {
    if (!practices.length) return []
    const result = []
    // Live practices first (most exciting), then recent sign-ups
    practices.forEach(p => {
      const ods = p.ods.toUpperCase()
      if (fullPlannerOds.has(ods)) {
        result.push({ name: p.name, status: 'live', label: 'Live' })
      } else if (liveOds.has(ods)) {
        result.push({ name: p.name, status: 'live', label: 'Live' })
      } else if (waitlistOds.has(ods)) {
        result.push({ name: p.name, status: 'signup', label: 'Signed Up' })
      }
    })
    return result
  }, [practices, liveOds, fullPlannerOds, waitlistOds])

  if (items.length === 0) return null

  // Duplicate the list so the scroll loops seamlessly
  return (
    <div className="practice-ticker">
      <div className="ticker-track">
        {[...items, ...items].map((item, i) => (
          <span className="ticker-item" key={i}>
            <span className={`ticker-dot ${item.status}`} />
            <span className="ticker-name">{item.name}</span>
            <span className={`ticker-label ${item.status}`}>{item.label}</span>
          </span>
        ))}
      </div>
    </div>
  )
}
