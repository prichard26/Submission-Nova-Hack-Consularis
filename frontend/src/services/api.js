/**
 * Shared API client for Consularis backend.
 * Base URL from env (VITE_API_BASE) or default for local dev.
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

async function buildError(res) {
  const text = await res.text()
  let detail = text
  try {
    const json = JSON.parse(text)
    detail = json.detail ?? json.message ?? text
  } catch (parseErr) {
    void parseErr
  }
  const err = new Error(detail || `Request failed: ${res.status}`)
  err.status = res.status
  err.response = res
  return err
}

async function request(path, options = {}) {
  const { parseAs = 'json', headers = {}, ...rest } = options
  const url = `${API_BASE}${path}`
  const hasJsonBody = typeof rest.body === 'string'
  const res = await fetch(url, {
    ...rest,
    headers: {
      ...(hasJsonBody ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
  })
  if (!res.ok) {
    throw await buildError(res)
  }
  if (parseAs === 'text') return res.text()
  return res.json()
}

// ---------------------------------------------------------------------------
// JSON-native graph endpoints
// ---------------------------------------------------------------------------

export function getGraphJson(sessionId, options = {}) {
  const { processId, ...rest } = options
  const sid = encodeURIComponent(sessionId)
  const pid = processId ? `&process_id=${encodeURIComponent(processId)}` : ''
  return request(`/api/graph/json?session_id=${sid}${pid}`, rest)
}

export function getBaselineJson(options = {}) {
  const { processId, ...rest } = options
  const pid = processId ? `?process_id=${encodeURIComponent(processId)}` : ''
  return request(`/api/graph/baseline/json${pid}`, rest)
}

export function getWorkspace(sessionId, options = {}) {
  const sid = encodeURIComponent(sessionId)
  return request(`/api/graph/workspace?session_id=${sid}`, options)
}

export function updateStepFields(sessionId, processId, stepId, updates, options = {}) {
  const sid = encodeURIComponent(sessionId)
  const pid = encodeURIComponent(processId)
  return request(`/api/graph/step?session_id=${sid}&process_id=${pid}`, {
    ...options,
    method: 'POST',
    body: JSON.stringify({ step_id: stepId, updates }),
  })
}

export function updatePositions(sessionId, processId, positions, options = {}) {
  const sid = encodeURIComponent(sessionId)
  const pid = encodeURIComponent(processId)
  return request(`/api/graph/position?session_id=${sid}&process_id=${pid}`, {
    ...options,
    method: 'POST',
    body: JSON.stringify({ positions }),
  })
}

export function createNode(sessionId, processId, laneId, name, type = 'step', position = null, options = {}) {
  const sid = encodeURIComponent(sessionId)
  const pid = encodeURIComponent(processId)
  return request(`/api/graph/node?session_id=${sid}&process_id=${pid}`, {
    ...options,
    method: 'POST',
    body: JSON.stringify({ lane_id: laneId, name, type, position }),
  })
}

export function createSubprocessPage(sessionId, processId, nodeId, name, parentProcessId = null, options = {}) {
  const sid = encodeURIComponent(sessionId)
  const pid = encodeURIComponent(processId)
  return request(`/api/graph/subprocess/create?session_id=${sid}&process_id=${pid}`, {
    ...options,
    method: 'POST',
    body: JSON.stringify({
      node_id: nodeId,
      name,
      parent_process_id: parentProcessId,
    }),
  })
}

export function createEdge(sessionId, processId, source, target, label = '', handles = {}, options = {}) {
  const { sourceHandle = null, targetHandle = null } = handles
  const sid = encodeURIComponent(sessionId)
  const pid = encodeURIComponent(processId)
  return request(`/api/graph/edge?session_id=${sid}&process_id=${pid}`, {
    ...options,
    method: 'POST',
    body: JSON.stringify({
      source,
      target,
      label,
      source_handle: sourceHandle,
      target_handle: targetHandle,
    }),
  })
}

export function deleteEdge(sessionId, processId, source, target, options = {}) {
  const sid = encodeURIComponent(sessionId)
  const pid = encodeURIComponent(processId)
  return request(
    `/api/graph/edge?session_id=${sid}&process_id=${pid}&source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`,
    { ...options, method: 'DELETE' },
  )
}

export function updateEdge(sessionId, processId, source, target, updates = {}, options = {}) {
  const sid = encodeURIComponent(sessionId)
  const pid = encodeURIComponent(processId)
  return request(`/api/graph/edge?session_id=${sid}&process_id=${pid}`, {
    ...options,
    method: 'PUT',
    body: JSON.stringify({
      source,
      target,
      label: updates.label ?? null,
      condition: updates.condition ?? null,
    }),
  })
}

export function deleteNode(sessionId, processId, nodeId, options = {}) {
  const sid = encodeURIComponent(sessionId)
  const pid = encodeURIComponent(processId)
  return request(
    `/api/graph/node?session_id=${sid}&process_id=${pid}&node_id=${encodeURIComponent(nodeId)}`,
    { ...options, method: 'DELETE' },
  )
}

// ---------------------------------------------------------------------------
// BPMN export (download only)
// ---------------------------------------------------------------------------

export function exportBpmnXml(sessionId, options = {}) {
  const { processId, ...rest } = options
  const sid = encodeURIComponent(sessionId)
  const pid = processId ? `&process_id=${encodeURIComponent(processId)}` : ''
  return request(`/api/graph/export?session_id=${sid}${pid}`, { ...rest, parseAs: 'text' })
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export function sendChat(sessionId, message, options = {}) {
  const { processId, ...rest } = options
  return request('/api/chat', {
    ...rest,
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, message, process_id: processId || null }),
  })
}

// ---------------------------------------------------------------------------
// Undo
// ---------------------------------------------------------------------------

export function undoGraph(sessionId, options = {}) {
  const { processId, ...rest } = options
  const sid = encodeURIComponent(sessionId)
  const pid = processId ? `&process_id=${encodeURIComponent(processId)}` : ''
  return request(`/api/graph/undo?session_id=${sid}${pid}`, {
    ...rest,
    method: 'POST',
  })
}

export function redoGraph(sessionId, options = {}) {
  const { processId, ...rest } = options
  const sid = encodeURIComponent(sessionId)
  const pid = processId ? `&process_id=${encodeURIComponent(processId)}` : ''
  return request(`/api/graph/redo?session_id=${sid}${pid}`, {
    ...rest,
    method: 'POST',
  })
}

export function resetToBaseline(sessionId, options = {}) {
  const { processId, ...rest } = options
  const sid = encodeURIComponent(sessionId)
  const pid = processId ? `&process_id=${encodeURIComponent(processId)}` : ''
  return request(`/api/graph/reset?session_id=${sid}${pid}`, {
    ...rest,
    method: 'POST',
  })
}
