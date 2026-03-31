export default function TopBar({ lastUpdated }) {
  return (
    <div className="top-bar">
      <div className="logo-section">
        <img src="/assets/suvera-logo.png" alt="Suvera" />
        <div className="title-group">
          <h1>GP Practice Growth Dashboard</h1>
          <div className="subtitle">England - Technology Led Growth</div>
        </div>
      </div>
      <div className="live-badge">
        <div className="dot"></div>
        <span>Last updated: {lastUpdated}</span>
      </div>
    </div>
  )
}
