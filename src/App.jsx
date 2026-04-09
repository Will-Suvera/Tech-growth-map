import TopBar from './components/TopBar'
import StatsPanel from './components/StatsPanel'
import DashboardMap from './components/DashboardMap'
import LoadingOverlay from './components/LoadingOverlay'
import { useDashboardData } from './hooks/useDashboardData'
import { useTimeline } from './hooks/useTimeline'

export default function App() {
  const { practices, liveOds, waitlistOds, loading, error, setLiveOds, setWaitlistOds } = useDashboardData()
  const timeline = useTimeline()

  const lastUpdated = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })

  // When timeline slider is not at the latest entry, use the timeline's aggregate
  // counts to override the stats panel (since individual snapshot ODS files may not exist)
  const isLatest = timeline.timelineData.length === 0 || timeline.sliderIdx === timeline.timelineData.length - 1
  const timelineOverride = !isLatest ? timeline.currentEntry : null

  return (
    <>
      <TopBar lastUpdated={lastUpdated} />
      <div className="main-layout">
        {loading || error ? (
          <>
            <div className="stats-panel" />
            <div className="map-container">
              <LoadingOverlay error={error} />
            </div>
          </>
        ) : (
          <>
            <StatsPanel
              practices={practices}
              liveOds={liveOds}
              waitlistOds={waitlistOds}
              timelineOverride={timelineOverride}
            />
            <DashboardMap
              practices={practices}
              liveOds={liveOds}
              waitlistOds={waitlistOds}
              setLiveOds={setLiveOds}
              setWaitlistOds={setWaitlistOds}
              timeline={timeline}
            />
          </>
        )}
      </div>
    </>
  )
}
