/**
 * Shared API client for Consularis backend.
 * Base URL from env (VITE_API_BASE) or default for local dev.
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
  if (!res.ok) {
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
    throw err
  }
  return res.json()
}

const API_BASE_FOR_TEXT = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/**
 * Fetch the baseline BPMN 2.0 XML (raw file). Use to display the unmodified base graph.
 * @returns {Promise<string>} BPMN XML string
 */
export async function getBaselineBpmnXml() {
  const url = `${API_BASE_FOR_TEXT}/api/graph/baseline`
  console.log('[getBaselineBpmnXml] Fetching baseline', { url })
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    console.error('[getBaselineBpmnXml] Failed', { status: res.status, body: text?.slice(0, 200) })
    throw new Error(text || `Request failed: ${res.status}`)
  }
  console.log('[getBaselineBpmnXml] OK', { xmlLength: text?.length })
  return text
}

/**
 * Fetch the graph as BPMN 2.0 XML for the session.
 * @param {string} sessionId - Session id (e.g. company name)
 * @returns {Promise<string>} BPMN XML string
 */
export async function getBpmnXml(sessionId) {
  const sid = encodeURIComponent(sessionId)
  const url = `${API_BASE_FOR_TEXT}/api/graph/export?session_id=${sid}`
  console.log('[getBpmnXml] Fetching graph', { sessionId, url })
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    console.error('[getBpmnXml] Failed', { status: res.status, body: text?.slice(0, 200) })
    throw new Error(text || `Request failed: ${res.status}`)
  }
  console.log('[getBpmnXml] OK', { sessionId, xmlLength: text?.length, preview: text?.slice(0, 80) })
  return text
}

/**
 * Fetch the session graph as JSON for custom renderers.
 * @param {string} sessionId - Session id (e.g. company name)
 * @returns {Promise<object>} graph payload with lanes, nodes, edges, and layout
 */
export function getGraphJson(sessionId) {
  const sid = encodeURIComponent(sessionId)
  return request(`/api/graph/json?session_id=${sid}`)
}

/**
 * Send a chat message and get the assistant reply and updated BPMN XML.
 * @param {string} sessionId - Session id
 * @param {string} message - User message
 * @returns {Promise<{ message: string, bpmn_xml: string, meta: object }>}
 */
export function sendChat(sessionId, message) {
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, message }),
  })
}
