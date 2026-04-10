import { useMemo } from 'react'
import { ANNUAL_TARGET, PATIENT_TARGET, QUARTERLY_TARGETS } from '../constants'
import AnimatedNumber from './AnimatedNumber'
import Sparkline from './Sparkline'
import NewThisWeekBadge from './NewThisWeekBadge'
import MilestoneProgressBar from './MilestoneProgressBar'

function MomBadge({ current, previous }) {
  if (previous == null || previous === 0 || current === previous) return null
  const delta = current - previous
  const pct = Math.round((delta / previous) * 100)
  if (pct === 0) return null
  const arrow = pct > 0 ? '↑' : '↓'
  const cls = pct > 0 ? 'mom-up' : 'mom-down'
  return <div className={`mom-badge ${cls}`}>{arrow}{Math.abs(pct)}% MoM</div>
}

export default function StatsPanel({ practices, liveOds, fullPlannerOds, waitlistOds, waitlistContacts, timelineOverride, timelineData }) {
  const liveStats = useMemo(() => {
    let fullPlannerCount = 0, plannerCount = 0, waitlistCount = 0
    let fullPlannerPatients = 0, plannerPatients = 0, waitlistPatients = 0
    practices.forEach(p => {
      const ods = p.ods.toUpperCase()
      const pat = p.patients || 0
      if (fullPlannerOds.has(ods)) { fullPlannerCount++; fullPlannerPatients += pat }
      else if (liveOds.has(ods)) { plannerCount++; plannerPatients += pat }
      else if (waitlistOds.has(ods)) { waitlistCount++; waitlistPatients += pat }
    })
    const liveCount = fullPlannerCount + plannerCount
    const livePatients = fullPlannerPatients + plannerPatients
    const pipeline = liveCount + waitlistCount
    const pct = Math.round((pipeline / ANNUAL_TARGET) * 100)
    const coverage = practices.length ? ((pipeline / practices.length) * 100).toFixed(1) : '0.0'
    return { fullPlannerCount, plannerCount, liveCount, waitlistCount, fullPlannerPatients, plannerPatients, livePatients, waitlistPatients, pipeline, pct, coverage }
  }, [practices, liveOds, fullPlannerOds, waitlistOds])

  const stats = useMemo(() => {
    if (!timelineOverride) return liveStats
    const { practices: tp, patients: tpat } = timelineOverride
    const pipeline = tp.pipeline
    const pct = Math.round((pipeline / ANNUAL_TARGET) * 100)
    const coverage = tp.total ? ((pipeline / tp.total) * 100).toFixed(1) : '0.0'
    return {
      fullPlannerCount: tp.live_full_planner ?? 0,
      plannerCount: tp.live_planner ?? 0,
      liveCount: tp.live ?? ((tp.live_full_planner || 0) + (tp.live_planner || 0)),
      waitlistCount: tp.waitlist,
      fullPlannerPatients: tpat.live_full_planner ?? 0,
      plannerPatients: tpat.live_planner ?? 0,
      livePatients: tpat.live ?? ((tpat.live_full_planner || 0) + (tpat.live_planner || 0)),
      waitlistPatients: tpat.waitlist,
      pipeline,
      pct,
      coverage,
    }
  }, [liveStats, timelineOverride])

  const prevMonth = useMemo(() => {
    if (!timelineData || timelineData.length < 2) return null
    const now = new Date()
    const target = new Date(now)
    target.setDate(target.getDate() - 30)
    let best = null
    let bestDiff = Infinity
    for (const e of timelineData) {
      const diff = Math.abs(new Date(e.date) - target)
      if (diff < bestDiff) { bestDiff = diff; best = e }
    }
    return best
  }, [timelineData])

  // Sparkline data: last 12 timeline entries
  const sparklines = useMemo(() => {
    if (!timelineData || timelineData.length < 2) return {}
    const recent = timelineData.slice(-12)
    return {
      waitlist: recent.map(e => e.practices.waitlist),
      liveTotal: recent.map(e => e.practices.live),
      pipeline: recent.map(e => e.practices.pipeline),
    }
  }, [timelineData])

  const today = new Date()
  const totalPractices = timelineOverride ? timelineOverride.practices.total : practices.length

  return (
    <div className="stats-panel">
      {/* Patient lives */}
      <div className="hero-stat" style={{ background: '#1e2a4a', borderColor: '#2d3a5c' }}>
        <div className="label" style={{ color: '#94a3c4' }}>Patient Lives Covered</div>
        <div className="number" style={{ fontSize: 36, color: '#fff' }}>
          <AnimatedNumber value={stats.livePatients + stats.waitlistPatients} />
        </div>
        <div className="of-target" style={{ color: '#94a3c4' }}>
          of <span style={{ color: '#fff' }}>{PATIENT_TARGET.toLocaleString()}</span> target
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 14, paddingTop: 14, borderTop: '1px solid #2d3a5c' }}>
          <div style={{ flex: 1, textAlign: 'center' }}>
            <div style={{ fontSize: 18, fontWeight: 500, color: '#4ade80' }}><AnimatedNumber value={stats.livePatients} /></div>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: 1, color: '#94a3c4', marginTop: 2 }}>Live</div>
          </div>
          <div style={{ width: 1, background: '#2d3a5c' }}></div>
          <div style={{ flex: 1, textAlign: 'center' }}>
            <div style={{ fontSize: 18, fontWeight: 500, color: '#fbbf24' }}><AnimatedNumber value={stats.waitlistPatients} /></div>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: 1, color: '#94a3c4', marginTop: 2 }}>To Be Onboarded</div>
          </div>
        </div>
      </div>

      {/* Pipeline + Progress */}
      <div className="hero-stat">
        <div className="label">Total Active Pipeline</div>
        {(() => {
          const signupCount = timelineOverride ? stats.waitlistCount : (waitlistContacts || waitlistOds.size)
          const pipelineDisplay = stats.liveCount + signupCount
          return <>
            <NewThisWeekBadge timelineData={timelineData} currentValue={pipelineDisplay} />
            <div className="number"><AnimatedNumber value={pipelineDisplay} /></div>
            <div className="pipeline-breakdown">
              <span className="pb-item pb-live">{stats.fullPlannerCount} Full</span>
              <span className="pb-sep">+</span>
              <span className="pb-item pb-partial">{stats.plannerCount} Partial</span>
              <span className="pb-sep">+</span>
              <span className="pb-item pb-signup">{signupCount} Sign-Ups</span>
            </div>
          </>
        })()}
        <div className="of-target">of <span>{ANNUAL_TARGET.toLocaleString()}</span> target practices</div>
        <Sparkline data={sparklines.pipeline} color="#1e2a4a" height={32} />
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid #dce3f0' }}>
          <div className="section-title" style={{ marginBottom: 10 }}>Progress to Target</div>
          <MilestoneProgressBar current={stats.pipeline} target={ANNUAL_TARGET} pct={stats.pct} />
          <div className="progress-stats">
            <span className="pct">{stats.pct}%</span>
            <span>{Math.max(ANNUAL_TARGET - stats.pipeline, 0).toLocaleString()} remaining</span>
          </div>
        </div>
      </div>

      {/* Stat cards — 3 columns */}
      <div className="stat-cards three-col">
        <div className="stat-card live-full-planner">
          <div className="value"><AnimatedNumber value={stats.fullPlannerCount} /></div>
          <MomBadge current={stats.fullPlannerCount} previous={prevMonth?.practices?.live_full_planner} />
          <div className="label">Live - Full Planner</div>
        </div>
        <div className="stat-card live">
          <div className="value"><AnimatedNumber value={stats.plannerCount} /></div>
          <MomBadge current={stats.plannerCount} previous={prevMonth?.practices?.live_planner} />
          <div className="label">Live - Partial Planner</div>
        </div>
        <div className="stat-card waitlist">
          <div className="value"><AnimatedNumber value={timelineOverride ? stats.waitlistCount : (waitlistContacts || waitlistOds.size)} /></div>
          <MomBadge current={timelineOverride ? stats.waitlistCount : (waitlistContacts || waitlistOds.size)} previous={prevMonth?.practices?.waitlist} />
          <div className="label">Sign-Up List</div>
        </div>
      </div>

      {/* Coverage */}
      <div className="coverage-card">
        <div className="coverage-row">
          <div className="coverage-metric">
            <div className="coverage-value" style={{ color: '#7c3aed' }}>{stats.coverage}%</div>
            <div className="coverage-label">{stats.pipeline.toLocaleString()} of {totalPractices.toLocaleString()} practices</div>
          </div>
          <div className="coverage-sep"></div>
          <div className="coverage-metric">
            <div className="coverage-value" style={{ color: '#2563eb' }}><AnimatedNumber value={totalPractices} /></div>
            <div className="coverage-label">Total GP Practices</div>
          </div>
        </div>
        <div className="coverage-title">England Coverage</div>
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
        <div className="legend-item"><div className="legend-dot full-planner"></div><div><span>Live - Full Planner</span><div className="legend-desc">Booking links + Pathology enabled</div></div></div>
        <div className="legend-item"><div className="legend-dot live"></div><div><span>Live - Partial Planner</span><div className="legend-desc">Planner active, not full feature set</div></div></div>
        <div className="legend-item"><div className="legend-dot waitlist"></div><span>On Sign-Up List</span></div>
        <div className="legend-item"><div className="legend-dot not-signed"></div><span>Not Signed Up</span></div>
      </div>
    </div>
  )
}
