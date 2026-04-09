/**
 * Custom event for auth session loss.
 * Broadcast when a 401 response is received from the API.
 * AuthProvider listens for this event to trigger logout + redirect.
 */

export const AUTH_LOST_EVENT = 'flib:auth-lost'

export interface AuthLostDetail {
  returnUrl: string
}

export function broadcastSessionLost() {
  window.dispatchEvent(
    new CustomEvent<AuthLostDetail>(AUTH_LOST_EVENT, {
      detail: { returnUrl: window.location.pathname + window.location.search },
    })
  )
}
