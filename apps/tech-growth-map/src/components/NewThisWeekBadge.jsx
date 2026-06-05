import { useMemo } from 'react'

export default function NewThisWeekBadge({ timelineData }) {
  const delta = useMemo(() => {
    if (!timelineData || timelineData.length < 2) return 0
    const latest = timelineData[timelineData.length - 1]
    const now = new Date()
    const target = new Date(now)
    target.setDate(target.getDate() - 30)
    let best = null
    let bestDiff = Infinity
    for (const e of timelineData) {
      if (e === latest) continue
      const diff = Math.abs(new Date(e.date) - target)
      if (diff < bestDiff) { bestDiff = diff; best = e }
    }
    if (!best) return 0
    return latest.practices.pipeline - best.practices.pipeline
  }, [timelineData])

  if (delta <= 0) return null

  return <div className="new-this-week">+{delta} in last 30 days</div>
}
