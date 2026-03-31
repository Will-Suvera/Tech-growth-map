import { useState, useEffect } from 'react'

export function useDashboardData() {
  const [practices, setPractices] = useState([])
  const [liveOds, setLiveOds] = useState(new Set())
  const [waitlistOds, setWaitlistOds] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    async function load() {
      try {
        const [practicesResp, waitlistResp, liveResp] = await Promise.all([
          fetch('/data/practices_geocoded.json', { cache: 'no-cache' }),
          fetch('/data/waitlist_ods.json', { cache: 'no-cache' }),
          fetch('/data/live_customers.json', { cache: 'no-cache' }),
        ])

        const practicesData = await practicesResp.json()
        const waitlistArr = await waitlistResp.json()
        const liveArr = await liveResp.json()

        setPractices(practicesData)
        setLiveOds(new Set(liveArr.map(c => c.toUpperCase())))
        setWaitlistOds(new Set(waitlistArr.map(c => c.toUpperCase())))
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return { practices, liveOds, waitlistOds, loading, error, setLiveOds, setWaitlistOds }
}
