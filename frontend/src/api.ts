const configuredBase = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${configuredBase}${normalized}`
}

export function websocketUrl(path = '/ws/live'): string {
  if (/^wss?:\/\//i.test(path)) return path
  if (configuredBase) {
    return `${configuredBase.replace(/^http/, 'ws')}${path}`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(path), init)
}

