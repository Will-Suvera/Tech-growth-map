import { useState, useEffect, useRef } from 'react'

const isTest = typeof import.meta !== 'undefined' && import.meta.env?.MODE === 'test'

export default function AnimatedNumber({ value, duration = 1500, formatter }) {
  const [displayed, setDisplayed] = useState(value)
  const hasAnimated = useRef(false)
  const rafRef = useRef(null)
  const format = formatter || (n => Number(n).toLocaleString())

  useEffect(() => {
    if (isTest || hasAnimated.current) {
      setDisplayed(value)
      return
    }
    hasAnimated.current = true
    const start = performance.now()
    const from = 0
    const to = value

    function tick(now) {
      const elapsed = now - start
      const t = Math.min(elapsed / duration, 1)
      const eased = 1 - (1 - t) ** 3 // cubic ease-out
      setDisplayed(Math.round(from + (to - from) * eased))
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        setDisplayed(to)
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [value, duration])

  return <>{format(displayed)}</>
}
