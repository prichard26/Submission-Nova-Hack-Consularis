/**
 * Small SVG face for the chat header (Aurelius). talking toggles a CSS class for animation.
 */
import { memo } from 'react'
import './BotFace.css'

function BotFace({ talking = false, size = 28 }) {
  return (
    <svg
      className={`bot-face${talking ? ' bot-face--talking' : ''}`}
      viewBox="0 0 60 48"
      width={size}
      height={Math.round(size * 0.8)}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect
        className="bot-face__head"
        x="2" y="2" width="56" height="44"
        rx="12" ry="12"
      />
      <circle className="bot-face__eye-socket bot-face__eye-socket--left" cx="20" cy="20" r="7" />
      <circle className="bot-face__pupil bot-face__pupil--left" cx="20" cy="20" r="3.5" />
      <circle className="bot-face__eye-socket bot-face__eye-socket--right" cx="40" cy="20" r="7" />
      <circle className="bot-face__pupil bot-face__pupil--right" cx="40" cy="20" r="3.5" />
      <rect
        className="bot-face__mouth"
        x="22" y="33" width="16" height="4"
        rx="2"
      />
    </svg>
  )
}

export default memo(BotFace)
