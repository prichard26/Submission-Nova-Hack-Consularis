/**
 * Robot avatar for landing and chat: crown + face, optional typing animation (message) and speaking state.
 * size: 'normal' | 'small'. Used on landing and in chat header.
 */
import { memo, useState, useEffect } from 'react'
import './Robot.css'

const BLINK_INTERVAL_MS = 3000
const BLINK_DURATION_MS = 150
const TYPING_INTERVAL_MS = 30

function Robot({ speaking, message, size = 'normal' }) {
  const [displayedText, setDisplayedText] = useState('')
  const [blinking, setBlinking] = useState(false)

  useEffect(() => {
    const blinkInterval = setInterval(() => {
      setBlinking(true)
      setTimeout(() => setBlinking(false), BLINK_DURATION_MS)
    }, BLINK_INTERVAL_MS)
    return () => clearInterval(blinkInterval)
  }, [])

  useEffect(() => {
    if (!message) return
    setDisplayedText('')
    let i = 0
    const interval = setInterval(() => {
      setDisplayedText(message.slice(0, i + 1))
      i++
      if (i >= message.length) clearInterval(interval)
    }, TYPING_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [message])

  return (
    <div className={`robot-container robot-container--${size}`}>
      <div className={`robot ${speaking ? 'robot--speaking' : ''}`}>
        <div className="robot__crown">
          <svg viewBox="0 0 80 20" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M6 18C8 14 10 8 16 6C12 10 10 14 8 18" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.6"/>
            <path d="M12 16C14 12 18 6 24 5C20 8 16 12 14 16" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.7"/>
            <path d="M20 14C22 10 26 5 32 4C28 7 24 10 22 14" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.8"/>
            <path d="M28 12C30 9 34 5 38 4" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.9"/>
            <path d="M74 18C72 14 70 8 64 6C68 10 70 14 72 18" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.6"/>
            <path d="M68 16C66 12 62 6 56 5C60 8 64 12 66 16" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.7"/>
            <path d="M60 14C58 10 54 5 48 4C52 7 56 10 58 14" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.8"/>
            <path d="M52 12C50 9 46 5 42 4" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.9"/>
          </svg>
        </div>

        <div className="robot__antenna">
          <div className="robot__antenna-ball" />
          <div className="robot__antenna-stick" />
        </div>

        <div className="robot__head">
          <div className={`robot__eye robot__eye--left ${blinking ? 'blink' : ''}`}>
            <div className="robot__pupil" />
          </div>
          <div className={`robot__eye robot__eye--right ${blinking ? 'blink' : ''}`}>
            <div className="robot__pupil" />
          </div>
          <div className={`robot__mouth ${speaking ? 'robot__mouth--talking' : ''}`} />
        </div>

        <div className="robot__neck" />
        <div className="robot__body">
          <div className="robot__chest-light" />
          <div className="robot__chest-light robot__chest-light--2" />
          <div className="robot__chest-light robot__chest-light--3" />
          <div className="robot__emblem">SPQR</div>
        </div>

        <div className="robot__arm robot__arm--left">
          <div className="robot__hand" />
        </div>
        <div className="robot__arm robot__arm--right">
          <div className="robot__hand" />
        </div>
      </div>

      <div className="robot__name">Aurelius</div>

      {message && (
        <div className="speech-bubble">
          <div className="speech-bubble__content">
            <p className="speech-bubble__sizer" aria-hidden="true">{message}</p>
            <p className="speech-bubble__text">
              {displayedText}<span className="cursor-blink">|</span>
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

export default memo(Robot)
