import Cookies from 'js-cookie'

const TokenKey = 'Admin-Token'

export function getToken(): string | undefined {
  return Cookies.get(TokenKey)
}

export function setToken(token: string): string | undefined {
  return Cookies.set(TokenKey, token, { expires: 7, path: '/' })
}

export function removeToken(): void {
  Cookies.remove(TokenKey, { path: '/' })
}
