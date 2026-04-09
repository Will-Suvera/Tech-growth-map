export default function MapTopBar({
  liveCount,
  waitlistCount,
  timeline,
}) {
  const { timelineData, months, currentMonthIdx, sliderIdx, metric, setMetric, changeMonth, onSliderChange, currentEntry } = timeline

  const monthLabel = months[currentMonthIdx]
    ? new Date(months[currentMonthIdx].ym + '-01T00:00:00').toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
    : '--'

  const dateLabel = currentEntry
    ? new Date(currentEntry.date + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    : '--'

  return (
    <>
      {/* Status chips — top-right to avoid zoom control overlap */}
      <div className="map-status-chips">
        <div className="map-overlay-chip">
          <div className="legend-dot live" style={{ width: 10, height: 10 }}></div>
          <span>{liveCount}</span> Live
        </div>
        <div className="map-overlay-chip">
          <div className="legend-dot waitlist" style={{ width: 10, height: 10 }}></div>
          <span>{waitlistCount}</span> Sign-Up List
        </div>
      </div>

      {/* Timeline bar — floating at bottom of map */}
      <div className="timeline-bar">
        <div className="timeline-bar-inner">
          <div className="timeline-controls">
            <div className="month-picker">
              <button className="month-arrow" disabled={currentMonthIdx <= 0} onClick={() => changeMonth(-1)}>&larr;</button>
              <span className="month-label">{monthLabel}</span>
              <button className="month-arrow" disabled={currentMonthIdx >= months.length - 1} onClick={() => changeMonth(1)}>&rarr;</button>
            </div>
            <span className="timeline-date">{dateLabel}</span>
          </div>

          <div className="timeline-slider-wrap">
            <input
              type="range"
              min={0}
              max={timelineData.length - 1 || 0}
              value={sliderIdx}
              onChange={e => onSliderChange(Number(e.target.value))}
            />
          </div>

          <div className="timeline-controls">
            {currentEntry && (
              <div className="timeline-detail">
                {metric === 'practices' ? (
                  <>
                    <span className="detail-live">{currentEntry.practices.live} live</span>
                    <span className="detail-sep">{'\u2022'}</span>
                    <span className="detail-waitlist">{currentEntry.practices.waitlist} sign-ups</span>
                    <span className="detail-sep">{'\u2022'}</span>
                    <strong>{currentEntry.practices.pipeline} total</strong>
                  </>
                ) : (
                  <>
                    <span className="detail-live">{currentEntry.patients.live.toLocaleString()}</span>
                    <span className="detail-sep">{'\u2022'}</span>
                    <span className="detail-waitlist">{currentEntry.patients.waitlist.toLocaleString()}</span>
                    <span className="detail-sep">{'\u2022'}</span>
                    <strong>{currentEntry.patients.pipeline.toLocaleString()}</strong>
                  </>
                )}
              </div>
            )}
            <div className="timeline-metric-toggle">
              <button
                className={`timeline-btn ${metric === 'practices' ? 'active' : ''}`}
                onClick={() => setMetric('practices')}
              >
                Practices
              </button>
              <button
                className={`timeline-btn ${metric === 'patients' ? 'active' : ''}`}
                onClick={() => setMetric('patients')}
              >
                Patients
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
