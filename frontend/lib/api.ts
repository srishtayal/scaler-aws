const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
export const token = () => typeof window === 'undefined' ? '' : localStorage.getItem('r53_token') || ''
export async function api(path:string, options:RequestInit = {}) {
  const response = await fetch(BASE + path, { ...options, headers: {'Content-Type':'application/json', ...(token() ? {Authorization:`Bearer ${token()}`} : {}), ...options.headers } })
  if (!response.ok) { const b = await response.json().catch(()=>({})); throw new Error(b.detail || 'Something went wrong') }
  return response.status === 204 ? null : response.json()
}