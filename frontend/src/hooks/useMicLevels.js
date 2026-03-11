import { useState, useEffect, useRef } from 'react'

const BAR_COUNT = 5
const FFT_SIZE = 256
const SMOOTHING = 0.75
const MIN_SCALE = 0.35
const SCALE_RANGE = 1 - MIN_SCALE

/**
 * Live mic levels per bar (0–1) for the voice visualizer.
 * Returns null when inactive or when mic access fails.
 */
export function useMicLevels(active) {
  const [levels, setLevels] = useState(null)
  const refs = useRef({
    stream: null,
    context: null,
    analyser: null,
    dataArray: null,
    raf: null,
  })

  useEffect(() => {
    if (!active) {
      setLevels(null)
      return
    }

    let cancelled = false
    const r = refs.current

    async function run() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        r.stream = stream

        const context = new (window.AudioContext || window.webkitAudioContext)()
        r.context = context

        const source = context.createMediaStreamSource(stream)
        const analyser = context.createAnalyser()
        analyser.fftSize = FFT_SIZE
        analyser.smoothingTimeConstant = SMOOTHING
        source.connect(analyser)
        r.analyser = analyser

        const len = analyser.frequencyBinCount
        r.dataArray = new Uint8Array(len)
        const step = Math.floor(len / BAR_COUNT)

        function tick() {
          if (cancelled || !r.analyser || !r.dataArray) return
          r.analyser.getByteFrequencyData(r.dataArray)
          const data = r.dataArray
          const next = []
          for (let i = 0; i < BAR_COUNT; i += 1) {
            let sum = 0
            const start = i * step
            for (let j = 0; j < step; j += 1) sum += data[start + j] ?? 0
            const raw = sum / step / 255
            next.push(MIN_SCALE + raw * SCALE_RANGE)
          }
          setLevels(next)
          r.raf = requestAnimationFrame(tick)
        }
        r.raf = requestAnimationFrame(tick)
      } catch {
        setLevels(null)
      }
    }

    run()
    return () => {
      cancelled = true
      if (r.raf != null) {
        cancelAnimationFrame(r.raf)
        r.raf = null
      }
      if (r.stream) {
        r.stream.getTracks().forEach((t) => t.stop())
        r.stream = null
      }
      if (r.context) {
        r.context.close().catch(() => {})
        r.context = null
      }
      r.analyser = null
      r.dataArray = null
      setLevels(null)
    }
  }, [active])

  return levels
}
