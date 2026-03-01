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
    } catch (_) {}
    const err = new Error(detail || `Request failed: ${res.status}`)
    err.status = res.status
    err.response = res
    throw err
  }
  return res.json()
}

/**
 * Fetch the graph for a session.
 * @param {string} sessionId - Session id (e.g. company name)
 * @returns {Promise<{ phases: Array, flow_connections: Array }>}
 */
export function getGraph(sessionId) {
  const sid = encodeURIComponent(sessionId)
  return request(`/api/graph?session_id=${sid}`)
}

/**
 * Send a chat message and get the assistant reply and updated graph.
 * @param {string} sessionId - Session id
 * @param {string} message - User message
 * @returns {Promise<{ message: string, graph: object, meta: object }>}
 */
export function sendChat(sessionId, message) {
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, message }),
  })
}
