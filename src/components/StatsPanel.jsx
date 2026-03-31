import { useMemo } from 'react'
import { ANNUAL_TARGET, PATIENT_TARGET, QUARTERLY_TARGETS } from '../constants'

export default function StatsPanel({ practices, liveOds, waitlistOds, timelineOverride }) {
  const liveStats = useMemo(() => {
    let liveCount = 0, waitlistCount = 0, livePatients = 0, waitlistPatients = 0
    practices.forEach(p => {
      const ods = p.ods.toUpperCase()
      if (liveOds.has(ods)) { liveCount++; livePatients += (p.patients || 0) }
      else if (waitlistOds.has(ods)) { waitlistCount++; waitlistPatients += (p.patients || 0) }
    })
    const pipeline = liveCount + waitlistCount
    const pct = Math.round((pipeline / ANNUAL_TARGET) * 100)
    const coverage = practices.length ? ((pipeline / practices.length) * 100).toFixed(1) : '0.0'
    return { liveCount, waitlistCount, livePatients, waitlistPatients, pipeline, pct, coverage }
  }, [practices, liveOds, waitlistOds])

  // When timeline is scrubbed to a historical point, override with aggregate counts
  const stats = useMemo(() => {
    if (!timelineOverride) return liveStats
    const { practices: tp, patients: tpat } = timelineOverride
    const pipeline = tp.pipeline
    const pct = Math.round((pipeline / ANNUAL_TARGET) * 100)
    const coverage = tp.total ? ((pipeline / tp.total) * 100).toFixed(1) : '0.0'
    return {
      liveCount: tp.live,
      waitlistCount: tp.waitlist,
      livePatients: tpat.live,
      waitlistPatients: tpat.waitlist,
      pipeline,
      pct,
      coverage,
    }
  }, [liveStats, timelineOverride])

  const today = new Date()
  const totalPractices = timelineOverride ? timelineOverride.practices.total : practices.length

  return (
    <div className="stats-panel">
      {/* Patient lives */}
      <div className="hero-stat" style={{ background: '#1e2a4a', borderColor: '#2d3a5c' }}>
        <div className="label" style={{ color: '#94a3c4' }}>Patient Lives Covered</div>
        <div className="number" style={{ fontSize: 36, color: '#fff' }}>
          {(stats.livePatients + stats.waitlistPatients).toLocaleString()}
        </div>
        <div className="of-target" style={{ color: '#94a3c4' }}>
          of <span style={{ color: '#fff' }}>{PATIENT_TARGET.toLocaleString()}</span> target
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 14, paddingTop: 14, borderTop: '1px solid #2d3a5c' }}>
          <div style={{ flex: 1, textAlign: 'center' }}>
            <div style={{ fontSize: 18, fontWeight: 500, color: '#4ade80' }}>{stats.livePatients.toLocaleString()}</div>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: 1, color: '#94a3c4', marginTop: 2 }}>Live</div>
          </div>
          <div style={{ width: 1, background: '#2d3a5c' }}></div>
          <div style={{ flex: 1, textAlign: 'center' }}>
            <div style={{ fontSize: 18, fontWeight: 500, color: '#fbbf24' }}>{stats.waitlistPatients.toLocaleString()}</div>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: 1, color: '#94a3c4', marginTop: 2 }}>To Be Onboarded</div>
          </div>
        </div>
      </div>

      {/* Pipeline + Progress */}
      <div className="hero-stat">
        <div className="label">Total Pipeline</div>
        <div className="number">{stats.pipeline.toLocaleString()}</div>
        <div className="of-target">of <span>{ANNUAL_TARGET.toLocaleString()}</span> target practices</div>
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid #dce3f0' }}>
          <div className="section-title" style={{ marginBottom: 10 }}>Progress to Target</div>
          <div className="progress-bar-container">
            <div className="progress-bar-fill" style={{ width: `${Math.min(stats.pct, 100)}%` }}></div>
          </div>
          <div className="progress-stats">
            <span className="pct">{stats.pct}%</span>
            <span>{Math.max(ANNUAL_TARGET - stats.pipeline, 0).toLocaleString()} remaining</span>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div className="stat-cards">
        <div className="stat-card live"><div className="value">{stats.liveCount}</div><div className="label">Live Customers</div></div>
        <div className="stat-card waitlist"><div className="value">{stats.waitlistCount}</div><div className="label">Waitlist</div></div>
        <div className="stat-card total-practices"><div className="value">{totalPractices.toLocaleString()}</div><div className="label">Total Practices</div></div>
        <div className="stat-card coverage"><div className="value">{stats.coverage}%</div><div className="label">Coverage</div></div>
      </div>

      {/* Quarterly targets */}
      <div className="quarterly-section">
        <div className="section-title">2026 Quarterly Targets</div>
        {QUARTERLY_TARGETS.map((qt, i) => {
          const deadline = new Date(qt.deadline)
          const isPast = today > deadline
          const isCurrent = !isPast && (i === 0 || today > new Date(QUARTERLY_TARGETS[i - 1].deadline))
          const progress = Math.min((stats.pipeline / qt.target) * 100, 100)
          const achieved = stats.pipeline >= qt.target
          const cls = achieved ? 'achieved' : isCurrent ? 'on-track' : 'behind'
          return (
            <div className="quarter-row" key={qt.q}>
              <div className="quarter-label">{qt.q}</div>
              <div className="quarter-bar-container">
                <div className={`quarter-bar-fill ${cls}`} style={{ width: `${progress}%` }}></div>
              </div>
              <div className="quarter-target">
                <span className={`actual ${cls}`}>{achieved ? qt.target : stats.pipeline}</span> / {qt.target}
              </div>
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div className="legend">
        <div className="section-title">Map Legend</div>
        <div className="legend-item"><div className="legend-dot live"></div><span>Live Customer</span></div>
        <div className="legend-item"><div className="legend-dot waitlist"></div><span>On Waitlist</span></div>
        <div className="legend-item"><div className="legend-dot not-signed"></div><span>Not Signed Up</span></div>
      </div>
    </div>
  )
}
