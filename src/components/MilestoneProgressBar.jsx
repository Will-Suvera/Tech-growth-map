const MILESTONES = [100, 300, 500, 1000]

export default function MilestoneProgressBar({ current, target, pct }) {
  return (
    <div className="milestone-progress">
      <div className="progress-bar-container">
        <div className="progress-bar-fill" style={{ width: `${Math.min(pct, 100)}%` }}></div>
      </div>
      <div className="milestone-markers">
        {MILESTONES.map(m => {
          const pos = (m / target) * 100
          const achieved = current >= m
          return (
            <div key={m} style={{ left: `${pos}%` }} className="milestone-pos">
              <div className={`milestone-marker ${achieved ? 'achieved' : 'upcoming'}`} />
              <div className={`milestone-label ${achieved ? 'achieved' : ''}`}>{m}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
