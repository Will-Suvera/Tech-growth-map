import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatsPanel from './StatsPanel'
import { MOCK_PRACTICES, MOCK_LIVE_ODS, MOCK_FULL_PLANNER_ODS, MOCK_WAITLIST_ODS, MOCK_TIMELINE_DATA } from '../test/fixtures'

const liveOds = new Set(MOCK_LIVE_ODS.map(c => c.toUpperCase()))
const fullPlannerOds = new Set(MOCK_FULL_PLANNER_ODS.map(c => c.toUpperCase()))
const waitlistOds = new Set(MOCK_WAITLIST_ODS.map(c => c.toUpperCase()))

const defaultProps = { practices: MOCK_PRACTICES, liveOds, fullPlannerOds, waitlistOds }

function getStatCard(label) {
  const matches = screen.getAllByText(label)
  const el = matches.find(m => m.closest('.stat-card'))
  return el.closest('.stat-card')
}

describe('StatsPanel', () => {
  it('renders pipeline count in hero stat', () => {
    render(<StatsPanel {...defaultProps} />)
    const heroStats = document.querySelectorAll('.hero-stat')
    const pipelineHero = heroStats[1]
    expect(pipelineHero.querySelector('.number').textContent).toBe('4')
  })

  it('renders correct full planner count', () => {
    render(<StatsPanel {...defaultProps} />)
    const card = getStatCard('Live - Full Planner')
    expect(card.querySelector('.value').textContent).toBe('1')
  })

  it('renders correct partial planner count', () => {
    render(<StatsPanel {...defaultProps} />)
    const card = getStatCard('Live - Partial Planner')
    expect(card.querySelector('.value').textContent).toBe('1')
  })

  it('renders correct sign-up list count', () => {
    render(<StatsPanel {...defaultProps} />)
    const card = getStatCard('Sign-Up List')
    expect(card.querySelector('.value').textContent).toBe('2')
  })

  it('renders patient lives correctly', () => {
    render(<StatsPanel {...defaultProps} />)
    expect(screen.getByText('28,000')).toBeInTheDocument()
    expect(screen.getByText('13,000')).toBeInTheDocument()
    expect(screen.getByText('15,000')).toBeInTheDocument()
  })

  it('renders coverage card with practice and patient percentages', () => {
    render(<StatsPanel {...defaultProps} />)
    expect(screen.getByText('England Coverage')).toBeInTheDocument()
    expect(screen.getByText('80.0%')).toBeInTheDocument()
  })

  it('renders quarterly targets section', () => {
    render(<StatsPanel {...defaultProps} />)
    expect(screen.getByText('2026 Quarterly Targets')).toBeInTheDocument()
    expect(screen.getByText('Q1')).toBeInTheDocument()
    expect(screen.getByText('Q4')).toBeInTheDocument()
  })

  it('renders map legend with tier labels', () => {
    render(<StatsPanel {...defaultProps} />)
    expect(screen.getAllByText('Live - Full Planner').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Live - Partial Planner').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('On Sign-Up List')).toBeInTheDocument()
    expect(screen.getByText('Not Signed Up')).toBeInTheDocument()
  })

  it('handles empty practices gracefully', () => {
    render(<StatsPanel practices={[]} liveOds={new Set()} fullPlannerOds={new Set()} waitlistOds={new Set()} />)
    const heroStats = document.querySelectorAll('.hero-stat')
    expect(heroStats[1].querySelector('.number').textContent).toBe('0')
  })

  it('uses timelineOverride counts when provided', () => {
    const override = MOCK_TIMELINE_DATA[0]
    render(<StatsPanel {...defaultProps} timelineOverride={override} />)
    const heroStats = document.querySelectorAll('.hero-stat')
    expect(heroStats[1].querySelector('.number').textContent).toBe('2')

    const waitlistCard = getStatCard('Sign-Up List')
    expect(waitlistCard.querySelector('.value').textContent).toBe('1')

    expect(screen.getByText('8,000')).toBeInTheDocument()
  })

  it('renders 3-column stat card grid', () => {
    render(<StatsPanel {...defaultProps} />)
    const grid = document.querySelector('.stat-cards.three-col')
    expect(grid).not.toBeNull()
    expect(grid.querySelectorAll('.stat-card').length).toBe(3)
  })
})
