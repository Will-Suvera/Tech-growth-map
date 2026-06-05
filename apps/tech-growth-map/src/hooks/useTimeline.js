import { useState, useEffect, useCallback, useMemo } from 'react'

function getMonthsFromData(data) {
  const months = []
  const seen = new Set()
  data.forEach((d, i) => {
    const ym = d.date.substring(0, 7)
    if (!seen.has(ym)) {
      seen.add(ym)
      months.push({ ym, firstIdx: i, lastIdx: i })
    } else {
      months[months.length - 1].lastIdx = i
    }
  })
  return months
}

export function useTimeline() {
  const [timelineData, setTimelineData] = useState([])
  const [months, setMonths] = useState([])
  const [sliderIdx, setSliderIdx] = useState(0)
  const [metric, setMetric] = useState('practices')

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}snapshots/timeline.json`, { cache: 'no-cache' })
      .then(r => r.json())
      .then(data => {
        setTimelineData(data)
        const m = getMonthsFromData(data)
        setMonths(m)
        setSliderIdx(data.length - 1)
      })
      .catch(e => console.warn('Timeline not loaded:', e))
  }, [])

  // Derive currentMonthIdx from sliderIdx instead of storing independently
  const currentMonthIdx = useMemo(() => {
    if (!timelineData.length || !months.length) return 0
    const d = timelineData[sliderIdx]
    if (!d) return 0
    const ym = d.date.substring(0, 7)
    const idx = months.findIndex(m => m.ym === ym)
    return idx >= 0 ? idx : 0
  }, [sliderIdx, timelineData, months])

  const changeMonth = useCallback((dir) => {
    const next = currentMonthIdx + dir
    if (next < 0 || next >= months.length) return
    setSliderIdx(months[next].lastIdx)
  }, [currentMonthIdx, months])

  const onSliderChange = useCallback((idx) => {
    setSliderIdx(idx)
  }, [])

  const currentEntry = timelineData[sliderIdx] || null

  return useMemo(() => ({
    timelineData,
    months,
    currentMonthIdx,
    sliderIdx,
    metric,
    setMetric,
    changeMonth,
    onSliderChange,
    currentEntry,
  }), [timelineData, months, currentMonthIdx, sliderIdx, metric, setMetric, changeMonth, onSliderChange, currentEntry])
}
