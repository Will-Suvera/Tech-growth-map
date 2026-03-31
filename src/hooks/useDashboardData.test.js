import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDashboardData } from './useDashboardData'
import { MOCK_PRACTICES, MOCK_LIVE_ODS, MOCK_WAITLIST_ODS } from '../test/fixtures'

beforeEach(() => {
  vi.restoreAllMocks()
})

function mockFetchSuccess() {
  vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
    if (url.includes('practices_geocoded')) {
      return Promise.resolve({ json: () => Promise.resolve(MOCK_PRACTICES) })
    }
    if (url.includes('waitlist_ods')) {
      return Promise.resolve({ json: () => Promise.resolve(MOCK_WAITLIST_ODS) })
    }
    if (url.includes('live_customers')) {
      return Promise.resolve({ json: () => Promise.resolve(MOCK_LIVE_ODS) })
    }
    return Promise.reject(new Error(`Unexpected fetch: ${url}`))
  })
}

describe('useDashboardData', () => {
  it('starts in loading state', () => {
    mockFetchSuccess()
    const { result } = renderHook(() => useDashboardData())

    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBeNull()
    expect(result.current.practices).toEqual([])
  })

  it('loads all data and resolves to correct state', async () => {
    mockFetchSuccess()
    const { result } = renderHook(() => useDashboardData())

    await act(async () => {})

    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()
    expect(result.current.practices).toHaveLength(5)
    expect(result.current.liveOds).toBeInstanceOf(Set)
    expect(result.current.liveOds.size).toBe(2)
    expect(result.current.liveOds.has('A001')).toBe(true)
    expect(result.current.liveOds.has('A002')).toBe(true)
    expect(result.current.waitlistOds.size).toBe(2)
    expect(result.current.waitlistOds.has('A003')).toBe(true)
    expect(result.current.waitlistOds.has('A004')).toBe(true)
  })

  it('uppercases ODS codes', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
      if (url.includes('practices_geocoded')) {
        return Promise.resolve({ json: () => Promise.resolve(MOCK_PRACTICES) })
      }
      if (url.includes('waitlist_ods')) {
        return Promise.resolve({ json: () => Promise.resolve(['a003']) })
      }
      if (url.includes('live_customers')) {
        return Promise.resolve({ json: () => Promise.resolve(['a001']) })
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`))
    })

    const { result } = renderHook(() => useDashboardData())
    await act(async () => {})

    expect(result.current.liveOds.has('A001')).toBe(true)
    expect(result.current.waitlistOds.has('A003')).toBe(true)
  })

  it('sets error state on fetch failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network down'))

    const { result } = renderHook(() => useDashboardData())
    await act(async () => {})

    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe('Network down')
    expect(result.current.practices).toEqual([])
  })

  it('exposes setLiveOds and setWaitlistOds for timeline updates', async () => {
    mockFetchSuccess()
    const { result } = renderHook(() => useDashboardData())
    await act(async () => {})

    const newLive = new Set(['A005'])
    act(() => { result.current.setLiveOds(newLive) })
    expect(result.current.liveOds).toBe(newLive)
  })
})
