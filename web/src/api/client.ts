const BASE_URL = ''

function getInitData(): string {
  try {
    return window.Telegram?.WebApp?.initData || ''
  } catch {
    return ''
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const initData = getInitData()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }

  if (initData) {
    headers['Authorization'] = `tma ${initData}`
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!res.ok) {
    throw new Error(`API error: ${res.status}`)
  }

  return res.json()
}

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

  getDownloadUrl: (bookId: string, format: string) =>
    `/api/books/${bookId}/download/${format}`,

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
