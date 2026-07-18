import { env } from '../config/env'
import type { AuthSessionResponse, AuthUser, PasswordLoginRequest, RegisterRequest } from '../types/auth'

async function parseResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export async function getAuthSession(): Promise<AuthSessionResponse> {
  const res = await fetch(`${env.appApiBase}/auth/session`, {
    credentials: 'include',
  })
  return parseResponse<AuthSessionResponse>(res)
}

export async function loginWithPassword(input: PasswordLoginRequest): Promise<AuthUser> {
  const res = await fetch(`${env.appApiBase}/auth/login/password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(input),
  })
  const data = await parseResponse<{ user: AuthUser }>(res)
  return data.user
}

export async function logout(): Promise<void> {
  await fetch(`${env.appApiBase}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
}

export async function register(input: RegisterRequest): Promise<AuthUser> {
  const res = await fetch(`${env.appApiBase}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(input),
  })
  const data = await parseResponse<{ user: AuthUser }>(res)
  return data.user
}
