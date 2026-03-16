/**
 * useVoiceInput: Web Speech API (SpeechRecognition) for Aurelius chat.
 * Exposes isListening, transcript (final), interimTranscript, accumulatedLive, error, toggleListening.
 * Stops automatically after SILENCE_TIMEOUT_MS of no speech; accumulated live transcript is used as placeholder in the input.
 */
import { useState, useCallback, useRef, useEffect } from 'react'

const SpeechRecognitionAPI =
  typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)

const SILENCE_TIMEOUT_MS = 2000

const VOICE_ERRORS = {
  'not-allowed': 'Microphone access denied. Please allow microphone permissions.',
  'no-speech': 'No speech detected. Please try again.',
  network: 'Network error during speech recognition.',
  aborted: null,
}

function getVoiceErrorMessage(errorCode) {
  return VOICE_ERRORS[errorCode] ?? 'Speech recognition failed. Please try again.'
}

function clearSilenceTimeout(ref) {
  if (ref.current != null) {
    clearTimeout(ref.current)
    ref.current = null
  }
}

function scheduleSilenceStop(recognitionRef, timeoutRef, ms) {
  clearSilenceTimeout(timeoutRef)
  timeoutRef.current = setTimeout(() => {
    timeoutRef.current = null
    try {
      if (recognitionRef.current) recognitionRef.current.stop()
    } catch {
      /* ignore */
    }
  }, ms)
}

export function useVoiceInput() {
  const [isListening, setIsListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [interimTranscript, setInterimTranscript] = useState('')
  const [accumulatedLive, setAccumulatedLive] = useState('')
  const [error, setError] = useState(null)

  const recognitionRef = useRef(null)
  const accumulatedRef = useRef('')
  const silenceTimeoutRef = useRef(null)

  const isSupported = Boolean(SpeechRecognitionAPI)

  const resetTranscriptState = useCallback(() => {
    setTranscript('')
    setInterimTranscript('')
    setAccumulatedLive('')
    accumulatedRef.current = ''
  }, [])

  const stopListening = useCallback(() => {
    clearSilenceTimeout(silenceTimeoutRef)
    const rec = recognitionRef.current
    if (rec) {
      try {
        rec.abort()
      } catch {
        /* ignore */
      }
      recognitionRef.current = null
    }
    setIsListening(false)
    setInterimTranscript('')
  }, [])

  const startListening = useCallback(() => {
    if (!SpeechRecognitionAPI) return

    setError(null)
    resetTranscriptState()

    let rec = recognitionRef.current
    if (!rec) {
      rec = new SpeechRecognitionAPI()
      rec.continuous = true
      rec.interimResults = true
      rec.lang = 'en-US'

      rec.onresult = (event) => {
        scheduleSilenceStop(recognitionRef, silenceTimeoutRef, SILENCE_TIMEOUT_MS)

        let interim = ''
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const result = event.results[i]
          const text = result[0].transcript
          if (result.isFinal) {
            const sep = accumulatedRef.current ? ' ' : ''
            accumulatedRef.current += sep + text
            setAccumulatedLive(accumulatedRef.current)
          } else {
            interim += (interim ? ' ' : '') + text
          }
        }
        if (interim) setInterimTranscript(interim)
      }

      rec.onend = () => {
        clearSilenceTimeout(silenceTimeoutRef)
        setIsListening(false)
        setInterimTranscript('')
        setAccumulatedLive('')
        setTranscript(accumulatedRef.current)
      }

      rec.onerror = (event) => {
        clearSilenceTimeout(silenceTimeoutRef)
        const message = getVoiceErrorMessage(event.error)
        if (message) setError(message)
        setIsListening(false)
        setInterimTranscript('')
      }

      recognitionRef.current = rec
    }

    setIsListening(true)
    try {
      rec.start()
    } catch {
      setError('Could not start speech recognition.')
      setIsListening(false)
      return
    }
    scheduleSilenceStop(recognitionRef, silenceTimeoutRef, SILENCE_TIMEOUT_MS)
  }, [resetTranscriptState])

  const toggleListening = useCallback(() => {
    if (isListening) stopListening()
    else startListening()
  }, [isListening, startListening, stopListening])

  useEffect(() => {
    return () => {
      clearSilenceTimeout(silenceTimeoutRef)
      const rec = recognitionRef.current
      if (rec) {
        try {
          rec.abort()
        } catch {
          /* ignore */
        }
        recognitionRef.current = null
      }
    }
  }, [])

  return {
    isSupported,
    isListening,
    transcript,
    accumulatedLive,
    interimTranscript,
    error,
    startListening,
    stopListening,
    toggleListening,
  }
}
