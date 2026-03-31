import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatsPanel from './StatsPanel'
import { MOCK_PRACTICES, MOCK_LIVE_ODS, MOCK_WAITLIST_ODS, MOCK_TIMELINE_DATA } from '../test/fixtures'

const liveOds = new Set(MOCK_LIVE_ODS.map(c => c.toUpperCase()))
const waitlistOds = new Set(MOCK_WAITLIST_ODS.map(c => c.toUpperCase()))

function getStatCard(label) {
  const labelEl = screen.getByText(label)
  return labelEl.closest('.stat-card')
}

describe('StatsPanel', () => {
  it('renders pipeline count in hero stat', () => {
    render(<StatsPanel practices={MOCK_PRACTICES} liveOds={liveOds} waitlistOds={waitlistOds} />)
    const heroStats = document.querySelectorAll('.hero-stat')
    const pipelineHero = heroStats[1]
    expect(pipelineHero.querySelector('.number').textContent).toBe('4')
  })

  it('renders correct live customer count', () => {
    render(<StatsPanel practices={MOCK_PRACTICES} liveOds={liveOds} waitlistOds={waitlistOds} />)
    const card = getStatCard('Live Customers')
    expect(card.querySelector('.value').textContent).toBe('2')
  })

  it('renders correct waitlist count', () => {
    render(<StatsPanel practices={MOCK_PRACTICES} liveOds={liveOds} waitlistOds={waitlistOds} />)
    const card = getStatCard('Waitlist')
    expect(card.querySelector('.value').textContent).toBe('2')
  })

  it('renders total practices count', () => {
    render(<StatsPanel practices={MOCK_PRACTICES} liveOds={liveOds} waitlistOds={waitlistOds} />)
    const card = getStatCard('Total Practices')
    expect(card.querySelector('.value').textContent).toBe('5')
  })

  it('renders patient lives correctly', () => {
    render(<StatsPanel practices={MOCK_PRACTICES} liveOds={liveOds} waitlistOds={waitlistOds} />)
    expect(screen.getByText('28,000')).toBeInTheDocument()
    expect(screen.getByText('13,000')).toBeInTheDocument()
    expect(screen.getByText('15,000')).toBeInTheDocument()
  })

  it('renders coverage percentage', () => {
    render(<StatsPanel practices={MOCK_PRACTICES} liveOds={liveOds} waitlistOds={waitlistOds} />)
    const card = getStatCard('Coverage')
    expect(card.querySelector('.value').textContent).toBe('80.0%')
  })

  it('renders quarterly targets section', () => {
    render(<StatsPanel practices={MOCK_PRACTICES} liveOds={liveOds} waitlistOds={waitlistOds} />)
    expect(screen.getByText('2026 Quarterly Targets')).toBeInTheDocument()
    expect(screen.getByText('Q1')).toBeInTheDocument()
    expect(screen.getByText('Q4')).toBeInTheDocument()
  })

  it('renders map legend', () => {
    render(<StatsPanel practices={MOCK_PRACTICES} liveOds={liveOds} waitlistOds={waitlistOds} />)
    expect(screen.getByText('Live Customer')).toBeInTheDocument()
    expect(screen.getByText('On Waitlist')).toBeInTheDocument()
    expect(screen.getByText('Not Signed Up')).toBeInTheDocument()
  })

  it('handles empty practices gracefully', () => {
    render(<StatsPanel practices={[]} liveOds={new Set()} waitlistOds={new Set()} />)
    const heroStats = document.querySelectorAll('.hero-stat')
    expect(heroStats[1].querySelector('.number').textContent).toBe('0')
  })

  it('uses timelineOverride counts when provided', () => {
    const override = MOCK_TIMELINE_DATA[0] // 1 live, 1 waitlist, 2 pipeline
    render(
      <StatsPanel
        practices={MOCK_PRACTICES}
        liveOds={liveOds}
        waitlistOds={waitlistOds}
        timelineOverride={override}
      />
    )
    const heroStats = document.querySelectorAll('.hero-stat')
    // Pipeline should be 2 (from timeline), not 4 (from live data)
    expect(heroStats[1].querySelector('.number').textContent).toBe('2')

    const liveCard = getStatCard('Live Customers')
    expect(liveCard.querySelector('.value').textContent).toBe('1')

    const waitlistCard = getStatCard('Waitlist')
    expect(waitlistCard.querySelector('.value').textContent).toBe('1')

    // Patient lives from timeline: 5000 + 3000 = 8000
    expect(screen.getByText('8,000')).toBeInTheDocument()
  })

  it('shows timeline total practices when override provided', () => {
    const override = MOCK_TIMELINE_DATA[0] // total: 5
    render(
      <StatsPanel
        practices={MOCK_PRACTICES}
        liveOds={liveOds}
        waitlistOds={waitlistOds}
        timelineOverride={override}
      />
    )
    const card = getStatCard('Total Practices')
    expect(card.querySelector('.value').textContent).toBe('5')
  })
})
