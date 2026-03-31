export const ANNUAL_TARGET = 1500
export const PATIENT_TARGET = 10_000_000

export const QUARTERLY_TARGETS = [
  { q: 'Q1', target: 300, deadline: '2026-03-31' },
  { q: 'Q2', target: 600, deadline: '2026-06-30' },
  { q: 'Q3', target: 1000, deadline: '2026-09-30' },
  { q: 'Q4', target: 1500, deadline: '2026-12-31' },
]

export const MAP_CENTER = [52.8, -1.5]
export const MAP_ZOOM = 6

export const MARKER_STYLES = {
  live: { color: '#22c55e', fillColor: '#22c55e', radius: 5, fillOpacity: 0.9, weight: 1.5, opacity: 0.8 },
  waitlist: { color: '#f59e0b', fillColor: '#f59e0b', radius: 4, fillOpacity: 0.8, weight: 1.5, opacity: 0.8 },
  notSigned: { color: '#818cf8', fillColor: '#6366f1', radius: 3, fillOpacity: 0.5, weight: 0.5, opacity: 0.8 },
}

export const ICB_STYLES = {
  default: { color: '#1e2a4a', weight: 1.2, fillColor: 'rgba(30,42,74,0.04)', fillOpacity: 1 },
  hover: { color: '#1e2a4a', weight: 2, fillColor: 'rgba(30,42,74,0.1)', fillOpacity: 1 },
  active: { color: '#1e2a4a', weight: 2.5, fillColor: 'rgba(30,42,74,0.18)', fillOpacity: 1 },
}
