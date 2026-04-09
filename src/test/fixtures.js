export const MOCK_PRACTICES = [
  { ods: 'A001', name: 'Test Practice 1', postcode: 'SW1A 1AA', lat: 51.5, lng: -0.1, patients: 5000, pcn_name: 'PCN Alpha', pcn_code: 'P001', icb: 'ICB North' },
  { ods: 'A002', name: 'Test Practice 2', postcode: 'EC1A 1BB', lat: 51.6, lng: -0.2, patients: 8000, pcn_name: 'PCN Beta', pcn_code: 'P002', icb: 'ICB South' },
  { ods: 'A003', name: 'Test Practice 3', postcode: 'WC1A 1CC', lat: 51.7, lng: -0.3, patients: 3000 },
  { ods: 'A004', name: 'Test Practice 4', postcode: 'N1 1DD', lat: 51.8, lng: -0.4, patients: 12000, pcn_name: 'PCN Gamma', pcn_code: 'P003', icb: 'ICB East' },
  { ods: 'A005', name: 'Test Practice 5', postcode: 'SE1 1EE', lat: 51.4, lng: -0.05, patients: 6000 },
]

export const MOCK_LIVE_ODS = ['A001', 'A002']
export const MOCK_WAITLIST_ODS = ['A003', 'A004']

export const MOCK_TIMELINE_DATA = [
  {
    date: '2026-01-05',
    timestamp: '2026-01-05T08:00:00',
    practices: { live: 1, waitlist: 1, pipeline: 2, total: 5, coverage_pct: 40 },
    patients: { live: 5000, waitlist: 3000, pipeline: 8000 },
  },
  {
    date: '2026-01-12',
    timestamp: '2026-01-12T08:00:00',
    practices: { live: 1, waitlist: 2, pipeline: 3, total: 5, coverage_pct: 60 },
    patients: { live: 5000, waitlist: 11000, pipeline: 16000 },
  },
  {
    date: '2026-02-01',
    timestamp: '2026-02-01T08:00:00',
    practices: { live: 2, waitlist: 2, pipeline: 4, total: 5, coverage_pct: 80 },
    patients: { live: 13000, waitlist: 15000, pipeline: 28000 },
  },
  {
    date: '2026-02-15',
    timestamp: '2026-02-15T08:00:00',
    practices: { live: 2, waitlist: 3, pipeline: 5, total: 5, coverage_pct: 100 },
    patients: { live: 13000, waitlist: 21000, pipeline: 34000 },
  },
]
