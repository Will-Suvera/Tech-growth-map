import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTimeline } from './useTimeline'
import { MOCK_TIMELINE_DATA } from '../test/fixtures'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('useTimeline', () => {
  it('loads timeline data and initialises slider to last entry', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      json: () => Promise.resolve(MOCK_TIMELINE_DATA),
    })

    const { result } = renderHook(() => useTimeline())

    // Initially empty
    expect(result.current.timelineData).toEqual([])
    expect(result.current.sliderIdx).toBe(0)

    // Wait for fetch
    await act(async () => {})

    expect(result.current.timelineData).toHaveLength(4)
    expect(result.current.sliderIdx).toBe(3) // last entry
    expect(result.current.currentEntry.date).toBe('2026-02-15')
  })

  it('derives currentMonthIdx from sliderIdx', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      json: () => Promise.resolve(MOCK_TIMELINE_DATA),
    })

    const { result } = renderHook(() => useTimeline())
    await act(async () => {})

    // sliderIdx=3 is Feb 2026 → month index 1
    expect(result.current.currentMonthIdx).toBe(1)
    expect(result.current.months[1].ym).toBe('2026-02')

    // Move slider to Jan entry
    act(() => { result.current.onSliderChange(0) })
    expect(result.current.currentMonthIdx).toBe(0)
    expect(result.current.months[0].ym).toBe('2026-01')
  })

  it('changeMonth navigates and updates sliderIdx', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      json: () => Promise.resolve(MOCK_TIMELINE_DATA),
    })

    const { result } = renderHook(() => useTimeline())
    await act(async () => {})

    // Start at Feb (month 1), go back to Jan (month 0)
    act(() => { result.current.changeMonth(-1) })
    expect(result.current.currentMonthIdx).toBe(0)
    // sliderIdx should be lastIdx of Jan month
    expect(result.current.sliderIdx).toBe(result.current.months[0].lastIdx)
  })

  it('changeMonth does not go out of bounds', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      json: () => Promise.resolve(MOCK_TIMELINE_DATA),
    })

    const { result } = renderHook(() => useTimeline())
    await act(async () => {})

    // Try going forward past the last month
    act(() => { result.current.changeMonth(1) })
    expect(result.current.currentMonthIdx).toBe(1) // unchanged

    // Go to first month then try going back
    act(() => { result.current.changeMonth(-1) })
    act(() => { result.current.changeMonth(-1) })
    expect(result.current.currentMonthIdx).toBe(0) // clamped
  })

  it('metric toggles between practices and patients', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      json: () => Promise.resolve(MOCK_TIMELINE_DATA),
    })

    const { result } = renderHook(() => useTimeline())
    await act(async () => {})

    expect(result.current.metric).toBe('practices')
    act(() => { result.current.setMetric('patients') })
    expect(result.current.metric).toBe('patients')
  })

  it('handles fetch failure gracefully', async () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'))

    const { result } = renderHook(() => useTimeline())
    await act(async () => {})

    expect(result.current.timelineData).toEqual([])
    expect(result.current.currentEntry).toBeNull()
    consoleSpy.mockRestore()
  })

  it('handles empty timeline data', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      json: () => Promise.resolve([]),
    })

    const { result } = renderHook(() => useTimeline())
    await act(async () => {})

    expect(result.current.timelineData).toEqual([])
    expect(result.current.months).toEqual([])
    expect(result.current.currentMonthIdx).toBe(0)
    expect(result.current.currentEntry).toBeNull()
  })
})
