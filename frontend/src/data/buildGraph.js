import pharmacyData from './pharmacy_circuit.json'

const PHASE_COLORS = {
  'Prescription':              { bg: '#1e1509', border: '#e85d04', text: '#ff9a5c' },
  'Selection, Acquisition, and Reception': { bg: '#1a160d', border: '#d54d02', text: '#ff7a2e' },
  'Storage and Storage Management': { bg: '#16120c', border: '#b33d00', text: '#e06030' },
  'Distribution':              { bg: '#191511', border: '#c44000', text: '#e87040' },
  'Dispensing and Preparation':{ bg: '#1e1509', border: '#e85d04', text: '#ff9a5c' },
  'Administration':            { bg: '#1a1409', border: '#d54d02', text: '#ff7a2e' },
  'Monitoring and Waste Management': { bg: '#161210', border: '#a33500', text: '#d06030' },
}

// Layout: each phase stacks vertically, steps spread horizontally
const PHASE_ORDER = [
  'Prescription',
  'Selection, Acquisition, and Reception',
  'Storage and Storage Management',
  'Distribution',
  'Dispensing and Preparation',
  'Administration',
  'Monitoring and Waste Management',
]

const NODE_W = 200
const NODE_H = 90
const H_GAP  = 60
const V_GAP  = 80

export function buildGraphData(circuitData = null) {
  const data = circuitData || pharmacyData
  const phases = data.phases || []
  const flowConnections = data.flow_connections || []

  const nodes = []
  const edges = []

  // Build a map: stepId -> step data (with phase name)
  const stepMap = {}
  for (const phase of phases) {
    for (const step of phase.steps) {
      stepMap[step.id] = { ...step, phaseName: phase.name }
    }
  }

  // Calculate positions: one column per phase, steps side by side
  let phaseY = 40
  const phaseLayouts = {}

  for (const phase of phases) {
    const steps = phase.steps
    const totalW = steps.length * NODE_W + (steps.length - 1) * H_GAP
    const startX = -(totalW / 2)

    const stepXMap = {}
    steps.forEach((step, i) => {
      stepXMap[step.id] = startX + i * (NODE_W + H_GAP)
    })

    phaseLayouts[phase.id] = { y: phaseY, stepXMap }
    phaseY += NODE_H + V_GAP

    // Create nodes
    for (const step of steps) {
      const colors = PHASE_COLORS[phase.name] || { bg: '#1e1914', border: '#e85d04', text: '#ff9a5c' }
      nodes.push({
        id: step.id,
        type: 'stepNode',
        position: {
          x: stepXMap[step.id],
          y: phaseLayouts[phase.id].y,
        },
        data: {
          ...step,
          phaseName: phase.name,
          phaseId: phase.id,
          colors,
        },
      })
    }
  }

  // Create edges from flow_connections
  for (const conn of flowConnections) {
    const label = [conn.condition, conn.label].filter(Boolean).join(' · ')
    const fromStep = stepMap[conn.from]
    const toStep   = stepMap[conn.to]

    // Detect back-edges (e.g. P7.1 → P1.1 or P3.3 → P2.2)
    const fromPhaseIdx = PHASE_ORDER.indexOf(fromStep?.phaseName)
    const toPhaseIdx   = PHASE_ORDER.indexOf(toStep?.phaseName)
    const isBackEdge   = toPhaseIdx < fromPhaseIdx

    edges.push({
      id: `${conn.from}-${conn.to}`,
      source: conn.from,
      target: conn.to,
      label,
      type: isBackEdge ? 'smoothstep' : 'default',
      animated: isBackEdge,
      style: {
        stroke: conn.condition ? '#ff9a5c' : '#4a3f30',
        strokeWidth: conn.condition ? 1.5 : 1.5,
        strokeDasharray: conn.condition ? '5 3' : undefined,
      },
      labelStyle: { fill: '#c9bfb0', fontSize: 10, fontFamily: 'DM Sans, sans-serif' },
      labelBgStyle: { fill: '#1e1914', fillOpacity: 0.9 },
      markerEnd: { type: 'arrowclosed', color: conn.condition ? '#ff9a5c' : '#4a3f30' },
    })
  }

  return { nodes, edges, phases, stepMap }
}

export { pharmacyData }
