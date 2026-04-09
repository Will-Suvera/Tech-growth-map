import { useMemo } from 'react'

export default function NewThisWeekBadge({ timelineData, currentValue }) {
  const delta = useMemo(() => {
    if (!timelineData || timelineData.length < 2) return 0
    const now = new Date()
    const target = new Date(now)
    target.setDate(target.getDate() - 10)
    let best = null
    let bestDiff = Infinity
    for (const e of timelineData) {
      const diff = Math.abs(new Date(e.date) - target)
      if (diff < bestDiff) { bestDiff = diff; best = e }
    }
    if (!best) return 0
    return currentValue - best.practices.pipeline
  }, [timelineData, currentValue])

  if (delta <= 0) return null

  return <div className="new-this-week">+{delta} in last 10 days</div>
}
