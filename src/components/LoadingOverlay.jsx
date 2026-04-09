export default function LoadingOverlay({ error }) {
  if (error) {
    return (
      <div className="loading-overlay">
        <div style={{ color: '#ef4444', fontSize: 14 }}>
          Error loading data.<br />
          <small style={{ color: '#94a3b8' }}>{error}</small>
        </div>
      </div>
    )
  }

  return (
    <div className="loading-overlay">
      <div className="loading-spinner"></div>
      <div className="loading-text">Loading GP practices...</div>
    </div>
  )
}
