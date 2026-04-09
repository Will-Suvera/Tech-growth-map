import { useMemo } from 'react'

export default function Sparkline({ data, color, width = '100%', height = 28 }) {
  const points = useMemo(() => {
    if (!data || data.length < 2) return null
    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1
    const pad = 2
    const vw = 80
    const vh = 30
    const step = (vw - pad * 2) / (data.length - 1)
    return data.map((v, i) => {
      const x = pad + i * step
      const y = vh - pad - ((v - min) / range) * (vh - pad * 2)
      return `${x},${y}`
    }).join(' ')
  }, [data])

  if (!points) return null

  const areaPoints = `${points} 78,28 2,28`

  return (
    <div className="sparkline-wrap">
      <svg viewBox="0 0 80 30" preserveAspectRatio="none" width={width} height={height}>
        <polygon points={areaPoints} fill={color} opacity="0.1" />
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  )
}
