const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')
export const token = () => typeof window === 'undefined' ? '' : localStorage.getItem('r53_token') || ''
export async function api(path:string, options:RequestInit = {}) {
  const url = BASE + path
  let response: Response
  try {
    response = await fetch(url, { ...options, headers: {'Content-Type':'application/json', ...(token() ? {Authorization:`Bearer ${token()}`} : {}), ...options.headers } })
  } catch {
    throw new Error(`Cannot reach the API at ${BASE}. Check NEXT_PUBLIC_API_URL and that the backend is running.`)
  }
  if (!response.ok) { const b = await response.json().catch(()=>({})); throw new Error(b.detail || `API request failed (${response.status}) at ${path}`) }
  return response.status === 204 ? null : response.json()
}
