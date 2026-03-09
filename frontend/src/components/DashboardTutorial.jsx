import { useState, useEffect, useCallback } from 'react'
import Robot from './Robot'
import './DashboardTutorial.css'

const TUTORIAL_STORAGE_KEY = 'consularis_tutorial_done'

const STEPS = [
  {
    id: 'topbar',
    message: "This is the top bar. You'll find quick actions here—like switching to the process landscape or running automation analysis.",
  },
  {
    id: 'canvas',
    message: "This is your process graph. You can drag nodes, add steps and decisions with the floating toolbar, and connect flows. Chat with me to change it with words.",
  },
  {
    id: 'toolbar',
    message: "The floating toolbar lets you zoom, add steps, decisions, subprocesses, auto-arrange, undo, and export. Hover over any button with your mouse to see what it does.",
  },
  {
    id: 'minimap',
    message: "The minimap shows where you are in the global architecture. Click a process to jump to it.",
  },
  {
    id: 'panelHeader',
    message: "Here you see the current process path and name. Click a path segment to go up, or click the pencil to edit the process name.",
  },
  {
    id: 'panelElementInfo',
    message: "Element info: click on an element in the graph to see its details here. When none is selected, use this area as a reminder.",
  },
  {
    id: 'panelChat',
    message: "Chat with me here to change the graph with words. Describe what you want and I'll update the process.",
  },
]

export function getTutorialDone() {
  if (typeof window === 'undefined') return true
  try {
    return localStorage.getItem(TUTORIAL_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function setTutorialDone() {
  try {
    localStorage.setItem(TUTORIAL_STORAGE_KEY, '1')
  } catch {}
}

function getRefForStep(step, refs) {
  const {
    topbarRef,
    canvasRef,
    toolbarRef,
    minimapRef,
    panelHeaderRef,
    panelElementInfoRef,
    panelChatRef,
  } = refs
  switch (step) {
    case 0: return topbarRef
    case 1: return canvasRef
    case 2: return toolbarRef
    case 3: return minimapRef
    case 4: return panelHeaderRef
    case 5: return panelElementInfoRef
    case 6: return panelChatRef
    default: return null
  }
}

export default function DashboardTutorial({
  topbarRef,
  canvasRef,
  panelRef,
  toolbarRef,
  minimapRef,
  panelHeaderRef,
  panelElementInfoRef,
  panelChatRef,
  onClose,
}) {
  const [step, setStep] = useState(0)
  const [highlightRect, setHighlightRect] = useState(null)

  const updateHighlight = useCallback(() => {
    const ref = getRefForStep(step, {
      topbarRef,
      canvasRef,
      toolbarRef,
      minimapRef,
      panelHeaderRef,
      panelElementInfoRef,
      panelChatRef,
    })
    if (!ref?.current) {
      setHighlightRect(null)
      return
    }
    const el = ref.current
    const rect = el.getBoundingClientRect()
    setHighlightRect({
      top: rect.top,
      left: rect.left,
      width: rect.width,
      height: rect.height,
    })
  }, [step, topbarRef, canvasRef, toolbarRef, minimapRef, panelHeaderRef, panelElementInfoRef, panelChatRef])

  useEffect(() => {
    updateHighlight()
    const onResize = () => updateHighlight()
    window.addEventListener('resize', onResize)
    const raf = requestAnimationFrame(updateHighlight)
    return () => {
      window.removeEventListener('resize', onResize)
      cancelAnimationFrame(raf)
    }
  }, [updateHighlight])

  const handleNext = useCallback(() => {
    if (step < STEPS.length - 1) {
      setStep((s) => s + 1)
    } else {
      setTutorialDone()
      onClose?.()
    }
  }, [step, onClose])

  const handleBack = useCallback(() => {
    setStep((s) => Math.max(0, s - 1))
  }, [])

  const handleSkip = useCallback(() => {
    setTutorialDone()
    onClose?.()
  }, [onClose])

  const currentStepConfig = STEPS[step]
  const isLast = step === STEPS.length - 1

  return (
    <div className="dashboard-tutorial" role="dialog" aria-modal="true" aria-label="Quick tour" aria-describedby="tutorial-message">
      {/* Dimmed overlay with cutout */}
      <div className="dashboard-tutorial__backdrop">
        {highlightRect && (
          <>
            <div
              className="dashboard-tutorial__cutout"
              style={{
                top: highlightRect.top,
                left: highlightRect.left,
                width: highlightRect.width,
                height: highlightRect.height,
              }}
            />
            <div
              className="dashboard-tutorial__highlight"
              style={{
                top: highlightRect.top,
                left: highlightRect.left,
                width: highlightRect.width,
                height: highlightRect.height,
              }}
            />
          </>
        )}
      </div>

      {/* Center card */}
      <div className="dashboard-tutorial__card">
        <div className="dashboard-tutorial__robot">
          <Robot speaking={false} message="" size="small" />
        </div>
        <div className="dashboard-tutorial__content">
          <p id="tutorial-message" className="dashboard-tutorial__message">
            {currentStepConfig.message}
          </p>
          <div className="dashboard-tutorial__steps">
            {STEPS.map((_, i) => (
              <span
                key={i}
                className={`dashboard-tutorial__dot ${i === step ? 'dashboard-tutorial__dot--active' : ''}`}
                aria-hidden
              />
            ))}
          </div>
          <div className="dashboard-tutorial__actions">
            <button
              type="button"
              className="dashboard-tutorial__btn dashboard-tutorial__btn--secondary"
              onClick={handleSkip}
            >
              Skip
            </button>
            <div className="dashboard-tutorial__nav">
              <button
                type="button"
                className="dashboard-tutorial__btn dashboard-tutorial__btn--secondary"
                onClick={handleBack}
                disabled={step === 0}
              >
                Back
              </button>
              <button
                type="button"
                className="dashboard-tutorial__btn dashboard-tutorial__btn--primary"
                onClick={handleNext}
              >
                {isLast ? 'Done' : 'Next'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
