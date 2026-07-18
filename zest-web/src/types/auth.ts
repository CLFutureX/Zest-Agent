export type AuthUser = {
  id: string
  username: string
  display_name: string | null
  email: string | null
}

export type AuthSessionResponse = {
  authenticated: boolean
  user: AuthUser | null
}

export type PasswordLoginRequest = {
  account: string
  password: string
}

export type RegisterRequest = {
  username: string
  email: string
  password: string
}
