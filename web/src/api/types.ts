export interface BookBrief {
  id: string
  title: string
  author: string
  cover: string
}

export interface BookDetail {
  id: string
  title: string
  author: string
  cover: string
  formats: Record<string, string>
  size: string
  series: string
  year: string
  annotation: string
  genres: string[]
  rating: string
  author_link: string
  is_favorite: boolean
  shelf: string | null
}

export interface FavoriteItem {
  book_id: string
  title: string
  author: string
  cover: string
  shelf: string | null
  notes: string | null
  added_date: string
}

export interface DownloadItem {
  book_id: string
  title: string
  author: string
  cover: string
  format: string
  download_date: string
}

export interface SearchHistoryItem {
  command: string
  query: string
  results_count: number
  timestamp: string
}

export interface UserProfile {
  user_id: string
  username: string
  full_name: string
  first_seen: string
  search_count: number
  download_count: number
  favorites_count: number
  level_name: string
  level_index: number
  level_progress: number
}

export interface ShelfCounts {
  all: number
  want: number
  reading: number
  done: number
  recommend: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
}

export type ShelfKey = 'all' | 'want' | 'reading' | 'done' | 'recommend'

export const SHELF_LABELS: Record<ShelfKey, string> = {
  all: 'Все',
  want: 'Хочу прочитать',
  reading: 'Читаю',
  done: 'Прочитано',
  recommend: 'Рекомендую',
}

export const SHELF_ICONS: Record<ShelfKey, string> = {
  all: '📚',
  want: '📕',
  reading: '📗',
  done: '📘',
  recommend: '📙',
}

// Audiobook types
export interface AudiobookSearchResult {
  topic_id: string
  title: string
  size: string
  seeds: number
  leeches: number
  forum_name: string
}

export interface AudiobookTopicInfo {
  topic_id: string
  title: string
  description: string
  cover: string
  forum_name: string
  topic_url: string
  files: string[]
  audio_files: string[]
}

export interface AudiobookFileEntry {
  filename: string
  size_bytes: number
  index: number
}

export interface ListeningProgressItem {
  id: number
  topic_id: string
  title: string
  author: string
  current_chapter: number
  total_chapters: number
  updated_at: number
}

export interface DownloadQueueItem {
  task_id: number
  topic_id: string
  title: string
  filename: string
  status: string
}
