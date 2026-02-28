import { useState, useCallback, useMemo, useEffect } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import StepNode from '../components/StepNode'
import DetailDrawer from '../components/DetailDrawer'
import AureliusChat from '../components/AureliusChat'
import { buildGraphData } from '../data/buildGraph'
import './Dashboard.css'

const nodeTypes = { stepNode: StepNode }

const ALL_PHASES = 'All'

const API_BASE = 'http://localhost:8000'

export default function Dashboard({ companyName }) {
  const [graphSource, setGraphSource] = useState(null)

  const graphResult = useMemo(
    () => buildGraphData(graphSource ?? undefined),
    [graphSource]
  )
  const { nodes: initialNodes, edges: initialEdges, phases, stepMap } = graphResult

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  const [selectedStep, setSelectedStep] = useState(null)
  const [activePhase, setActivePhase] = useState(ALL_PHASES)
  const [chatOpen, setChatOpen] = useState(false)

  // Fetch graph from backend on mount (keeps session in sync)
  useEffect(() => {
    const sid = encodeURIComponent(companyName)
    fetch(`${API_BASE}/api/graph?session_id=${sid}`)
      .then((r) => r.json())
      .then(setGraphSource)
      .catch(() => setGraphSource(null))
  }, [companyName])

  // When graph source changes (e.g. after chat updates), sync React Flow state
  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [graphSource, initialNodes, initialEdges, setNodes, setEdges])

  const phaseNames = [ALL_PHASES, ...phases.map((p) => p.name)]

  const handleGraphUpdate = useCallback((newGraph) => {
    if (newGraph?.phases && newGraph?.flow_connections) {
      // Clone so React sees a new reference and the diagram definitely re-renders
      setGraphSource({ phases: newGraph.phases, flow_connections: newGraph.flow_connections })
    }
  }, [])

  // Filter nodes/edges for active phase
  const visibleNodes = useMemo(() => {
    if (activePhase === ALL_PHASES) return nodes
    return nodes.map(n => ({
      ...n,
      hidden: n.data.phaseName !== activePhase,
    }))
  }, [nodes, activePhase])

  const visibleEdges = useMemo(() => {
    if (activePhase === ALL_PHASES) return edges
    const visibleIds = new Set(
      visibleNodes.filter(n => !n.hidden).map(n => n.id)
    )
    return edges.map(e => ({
      ...e,
      hidden: !visibleIds.has(e.source) || !visibleIds.has(e.target),
    }))
  }, [edges, visibleNodes, activePhase])

  const onNodeClick = useCallback((_, node) => {
    setSelectedStep(node.data)
  }, [])

  const onPaneClick = useCallback(() => {
    setSelectedStep(null)
  }, [])

  // Short phase label for tab
  const shortPhase = (name) => {
    if (name === ALL_PHASES) return 'All'
    const map = {
      'Prescription': 'Prescription',
      'Selection, Acquisition, and Reception': 'Acquisition',
      'Storage and Storage Management': 'Storage',
      'Distribution': 'Distribution',
      'Dispensing and Preparation': 'Dispensing',
      'Administration': 'Administration',
      'Monitoring and Waste Management': 'Monitoring',
    }
    return map[name] || name.split(' ')[0]
  }

  const phaseShortId = (name) => {
    const idx = phases.findIndex(p => p.name === name)
    return idx >= 0 ? `P${idx + 1}` : ''
  }

  return (
    <div className="dashboard">
      {/* ── Top bar ── */}
      <header className="dashboard__topbar">
        <div className="dashboard__topbar-left">
          <span className="dashboard__logo">
            Consularis<span className="dashboard__logo-dot">.</span>
          </span>
          <span className="dashboard__company">{companyName}</span>
          <span className="dashboard__badge">Pharmacy</span>
        </div>

        <nav className="dashboard__phases">
          {phaseNames.map(name => (
            <button
              key={name}
              className={`phase-tab ${activePhase === name ? 'phase-tab--active' : ''}`}
              onClick={() => { setActivePhase(name); setSelectedStep(null) }}
            >
              {name !== ALL_PHASES && (
                <span className="phase-tab__id">{phaseShortId(name)}</span>
              )}
              {shortPhase(name)}
            </button>
          ))}
        </nav>

        <button
          className={`dashboard__chat-toggle ${chatOpen ? 'dashboard__chat-toggle--active' : ''}`}
          onClick={() => setChatOpen(o => !o)}
        >
          <span>🤖</span> Aurelius
        </button>
      </header>

      {/* ── Main canvas ── */}
      <div className="dashboard__canvas">
        <ReactFlow
          nodes={visibleNodes}
          edges={visibleEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.15}
          maxZoom={2}
          defaultEdgeOptions={{
            style: { stroke: '#4a3f30', strokeWidth: 1.5 },
            markerEnd: { type: 'arrowclosed', color: '#4a3f30' },
          }}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#2e2820" gap={32} size={1} />
          <Controls
            style={{ background: '#1e1914', border: '1px solid #2e2820' }}
            showInteractive={false}
          />
          <MiniMap
            nodeColor={n => n.data?.colors?.border || '#e85d04'}
            style={{ background: '#12100d', border: '1px solid #2e2820' }}
            maskColor="rgba(18,16,13,0.7)"
          />
        </ReactFlow>

        {/* Detail drawer (right side) */}
        {selectedStep && (
          <DetailDrawer
            step={selectedStep}
            onClose={() => setSelectedStep(null)}
          />
        )}
      </div>

      {/* ── Aurelius chat panel ── */}
      {chatOpen && (
        <AureliusChat
          sessionId={companyName}
          onGraphUpdate={handleGraphUpdate}
          onClose={() => setChatOpen(false)}
        />
      )}
    </div>
  )
}
