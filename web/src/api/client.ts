/**
 * API client — mirrors time_jedi_bot/web/frontend/src/api/client.ts
 *
 * - All requests go through a single `request()` helper
 * - Bearer token injected from localStorage
 * - 401 triggers session-lost broadcast → AuthProvider catches and redirects
 */

import { broadcastSessionLost } from '../lib/authSession'

const TOKEN_KEY = 'flib_token'

function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

// ── Core request helper ──

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(path, { ...options, headers })

  if (res.status === 401) {
    broadcastSessionLost()
    throw new Error('AUTH_EXPIRED')
  }

  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`API ${res.status}: ${body}`)
  }

  return res.json()
}

// ── Auth API (unauthenticated) ──

export async function loginWithInitData(
  initData: string
): Promise<{ access_token: string; user: Record<string, unknown> }> {
  const res = await fetch('/api/auth/telegram-webapp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data: initData }),
  })
  if (!res.ok) throw new Error(`Auth failed: ${res.status}`)
  return res.json()
}

export async function loginWithWidget(
  userData: Record<string, unknown>
): Promise<{ access_token: string; user: Record<string, unknown> }> {
  const res = await fetch('/api/auth/telegram-widget', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(userData),
  })
  if (!res.ok) throw new Error(`Auth failed: ${res.status}`)
  return res.json()
}

// ── Typed API (all authenticated) ──

export const api = {
  // Library
  getLibrary: (shelf?: string, page = 1, perPage = 20) =>
    request(`/api/library?${new URLSearchParams({ ...(shelf && shelf !== 'all' ? { shelf } : {}), page: String(page), per_page: String(perPage) })}`),

  getShelfCounts: () =>
    request('/api/library/counts'),

  addToLibrary: (bookId: string, body: { title: string; author: string; shelf?: string }) =>
    request(`/api/library/${bookId}`, { method: 'POST', body: JSON.stringify(body) }),

  removeFromLibrary: (bookId: string) =>
    request(`/api/library/${bookId}`, { method: 'DELETE' }),

  updateLibraryItem: (bookId: string, body: { shelf?: string; notes?: string }) =>
    request(`/api/library/${bookId}`, { method: 'PATCH', body: JSON.stringify(body) }),

  // Search
  searchBooks: (q: string, type = 'title', page = 1, perPage = 20) =>
    request(`/api/search?${new URLSearchParams({ q, type, page: String(page), per_page: String(perPage) })}`),

  getSearchHistory: (page = 1) =>
    request(`/api/search/history?page=${page}`),

  clearSearchHistory: () =>
    request('/api/search/history', { method: 'DELETE' }),

  // Books
  getBook: (bookId: string) =>
    request(`/api/books/${bookId}`),

  getRelatedBooks: (bookId: string) =>
    request(`/api/books/${bookId}/related`),

  getDownloadUrl: (bookId: string, format: string) => {
    const token = getToken()
    return `/api/books/${bookId}/download/${format}${token ? `?token=${encodeURIComponent(token)}` : ''}`
  },

  // Downloads
  getDownloads: (page = 1) =>
    request(`/api/downloads?page=${page}`),

  clearDownloads: () =>
    request('/api/downloads', { method: 'DELETE' }),

  // Profile
  getProfile: () =>
    request('/api/profile'),

  getPreferences: () =>
    request('/api/profile/preferences'),

  updatePreferences: (body: { default_format?: string; books_per_page?: number }) =>
    request('/api/profile/preferences', { method: 'PATCH', body: JSON.stringify(body) }),

  // Audiobooks
  searchAudiobooks: (q: string, limit = 15) =>
    request(`/api/audiobooks/search?${new URLSearchParams({ q, limit: String(limit) })}`),

  getAudiobookInfo: (topicId: string) =>
    request(`/api/audiobooks/${topicId}/info`),

  getAudiobookFiles: (topicId: string) =>
    request(`/api/audiobooks/${topicId}/files`),

  enqueueAudiobookDownload: (topicId: string) =>
    request(`/api/audiobooks/${topicId}/download`, { method: 'POST' }),

  getAudiobookQueue: () =>
    request('/api/audiobooks/queue'),

  getListeningProgress: () =>
    request('/api/audiobooks/progress'),

  updateAudioProgress: (topicId: string, body: { chapter: number }) =>
    request(`/api/audiobooks/progress/${topicId}`, { method: 'PATCH', body: JSON.stringify(body) }),
}

// ── Helper for streaming URLs (need token in query param) ──

export function getStreamUrl(topicId: string, fileIndex: number): string {
  const token = getToken()
  return `/api/audiobooks/${topicId}/stream/${fileIndex}${token ? `?token=${encodeURIComponent(token)}` : ''}`
}
