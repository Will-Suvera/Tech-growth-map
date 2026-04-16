import AnimatedNumber from './AnimatedNumber'

function monthLabel(isoMonth) {
  if (!isoMonth) return ''
  const d = new Date(isoMonth + '-01')
  return d.toLocaleDateString('en-GB', { month: 'short' })
}

function growthMultiple(monthly) {
  const keys = Object.keys(monthly || {}).sort()
  if (keys.length < 2) return null
  const latest = monthly[keys[keys.length - 1]]
  const prev = monthly[keys[keys.length - 2]]
  if (!prev || latest <= prev) return null
  return (latest / prev).toFixed(1)
}

export default function ActivityFloat({ recalls }) {
  if (!recalls) return null

  const r = recalls.recalls || { total: 0, monthly: {} }
  const b = recalls.bloods || { total: 0, monthly: {} }
  const rKeys = Object.keys(r.monthly || {}).sort()
  const bKeys = Object.keys(b.monthly || {}).sort()
  const rThisMonth = rKeys.length ? r.monthly[rKeys[rKeys.length - 1]] : 0
  const bThisMonth = bKeys.length ? b.monthly[bKeys[bKeys.length - 1]] : 0
  const rLabel = monthLabel(rKeys[rKeys.length - 1])
  const bLabel = monthLabel(bKeys[bKeys.length - 1])
  const rMult = growthMultiple(r.monthly)
  const bMult = growthMultiple(b.monthly)

  return (
    <div className="activity-float">
      <div className="af-header">
        <span className="af-pulse" />
        <span className="af-title">Patient Care Delivered</span>
      </div>
      <div className="af-metrics">
        <div className="af-metric">
          <div className="af-label">Recalls Sent</div>
          <div className="af-value af-recalls">
            <AnimatedNumber value={r.total} />
          </div>
          <div className="af-sub">
            <strong>+{rThisMonth.toLocaleString()}</strong> in {rLabel}
            {rMult && <span className="af-mult">&nbsp;·&nbsp;{rMult}× prev mo.</span>}
          </div>
        </div>
        <div className="af-divider" />
        <div className="af-metric">
          <div className="af-label">Bloods Automated</div>
          <div className="af-value af-bloods">
            <AnimatedNumber value={b.total} />
          </div>
          <div className="af-sub">
            <strong>+{bThisMonth.toLocaleString()}</strong> in {bLabel}
            {bMult && <span className="af-mult">&nbsp;·&nbsp;{bMult}× prev mo.</span>}
          </div>
        </div>
      </div>
    </div>
  )
}
