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

/**
 * Fetch the baseline BPMN 2.0 XML (raw file). Use to display the unmodified base graph.
 * @returns {Promise<string>} BPMN XML string
 */
export function getBaselineBpmnXml(options = {}) {
  const { processId, ...rest } = options
  const pid = processId ? `?process_id=${encodeURIComponent(processId)}` : ''
  return request(`/api/graph/baseline${pid}`, { ...rest, parseAs: 'text' })
}

/**
 * Fetch the graph as BPMN 2.0 XML for the session.
 * @param {string} sessionId - Session id (e.g. company name)
 * @returns {Promise<string>} BPMN XML string
 */
export function getBpmnXml(sessionId, options = {}) {
  const { processId, ...rest } = options
  const sid = encodeURIComponent(sessionId)
  const pid = processId ? `&process_id=${encodeURIComponent(processId)}` : ''
  return request(`/api/graph/export?session_id=${sid}${pid}`, { ...rest, parseAs: 'text' })
}

/**
 * Fetch the session graph as JSON for custom renderers.
 * @param {string} sessionId - Session id (e.g. company name)
 * @returns {Promise<object>} graph payload with lanes, nodes, edges, and layout
 */
export function getGraphJson(sessionId, options = {}) {
  const { processId, ...rest } = options
  const sid = encodeURIComponent(sessionId)
  const pid = processId ? `&process_id=${encodeURIComponent(processId)}` : ''
  return request(`/api/graph/json?session_id=${sid}${pid}`, rest)
}

export function getProcessTree(sessionId, options = {}) {
  const sid = encodeURIComponent(sessionId)
  return request(`/api/graph/processes?session_id=${sid}`, options)
}

export function resolveGraphStep(sessionId, name, options = {}) {
  const sid = encodeURIComponent(sessionId)
  const q = encodeURIComponent(name)
  const { processId, ...rest } = options
  const pid = processId ? `&process_id=${encodeURIComponent(processId)}` : ''
  return request(`/api/graph/resolve?session_id=${sid}&name=${q}${pid}`, rest)
}

/**
 * Send a chat message and get the assistant reply and updated BPMN XML.
 * @param {string} sessionId - Session id
 * @param {string} message - User message
 * @returns {Promise<{ message: string, bpmn_xml: string, meta: object }>}
 */
export function sendChat(sessionId, message, options = {}) {
  const { processId, ...rest } = options
  return request('/api/chat', {
    ...rest,
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, message, process_id: processId || null }),
  })
}
