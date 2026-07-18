const DEFAULT_APP_API_BASE = 'http://127.0.0.1:9000/api/v1'
const DEFAULT_WS_RECONNECT_MAX_RETRIES = 3
const DEFAULT_WS_RECONNECT_DELAY_MS = 1500

function readNumber(value: string | undefined, fallback: number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export const env = {
  appApiBase: import.meta.env.VITE_APP_API_BASE || DEFAULT_APP_API_BASE,
  wsReconnectMaxRetries: readNumber(
    import.meta.env.VITE_WS_RECONNECT_MAX_RETRIES,
    DEFAULT_WS_RECONNECT_MAX_RETRIES,
  ),
  wsReconnectDelayMs: readNumber(
    import.meta.env.VITE_WS_RECONNECT_DELAY_MS,
    DEFAULT_WS_RECONNECT_DELAY_MS,
  ),
}
