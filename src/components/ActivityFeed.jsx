import { useMemo } from 'react'

function fmtDate(dateStr) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export default function ActivityFeed({ timelineData }) {
  const entries = useMemo(() => {
    if (!timelineData || timelineData.length < 2) return []
    const items = []
    const recent = timelineData.slice(-6)
    for (let i = recent.length - 1; i > 0 && items.length < 4; i--) {
      const curr = recent[i]
      const prev = recent[i - 1]
      const dp = curr.practices.pipeline - prev.practices.pipeline
      const dw = curr.practices.waitlist - prev.practices.waitlist
      const dl = curr.practices.live - prev.practices.live
      const dateRange = `${fmtDate(prev.date)} – ${fmtDate(curr.date)}`

      if (dp > 0) {
        const parts = []
        if (dl > 0) parts.push(`${dl} go-live`)
        if (dw > 0) parts.push(`${dw} sign-ups`)
        const detail = parts.length ? ` (${parts.join(', ')})` : ''
        items.push({ key: curr.date, delta: `+${dp} practices${detail}`, dateRange })
      } else if (dp === 0 && (dw > 0 || dl > 0)) {
        const parts = []
        if (dl > 0) parts.push(`+${dl} go-live`)
        if (dw > 0) parts.push(`+${dw} sign-ups`)
        items.push({ key: curr.date, delta: parts.join(', '), dateRange })
      }
    }
    return items
  }, [timelineData])

  if (entries.length === 0) return null

  return (
    <div className="activity-feed">
      <div className="section-title">Recent Activity</div>
      {entries.map(e => (
        <div className="activity-item" key={e.key}>
          <span className="activity-delta">{e.delta}</span>
          <span className="activity-date">{e.dateRange}</span>
        </div>
      ))}
    </div>
  )
}
