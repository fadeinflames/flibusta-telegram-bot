import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '../api/client'
import { useHaptic } from '../hooks/useTelegram'
import { staggerContainer, staggerItem } from '../lib/animations'
import type { PaginatedResponse, FavoriteItem, DownloadItem } from '../api/types'
import BookCoverCard from '../components/books/BookCoverCard'
import HorizontalCarousel from '../components/books/HorizontalCarousel'

const READING_PROGRESS_KEY = 'fb2_reader_settings'

function getReadingProgress(): Record<string, { chapter: number; scrollPercent: number }> {
  try {
    const raw = localStorage.getItem(READING_PROGRESS_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return parsed.progress || {}
    }
  } catch { /* ignore */ }
  return {}
}

export default function DiscoveryPage() {
  const navigate = useNavigate()
  const { selection } = useHaptic()

  const readingBooks = useQuery<PaginatedResponse<FavoriteItem>>({
    queryKey: ['library', 'reading', 1],
    queryFn: () => api.getLibrary('reading', 1, 20) as Promise<PaginatedResponse<FavoriteItem>>,
  })

  const wantBooks = useQuery<PaginatedResponse<FavoriteItem>>({
    queryKey: ['library', 'want', 1],
    queryFn: () => api.getLibrary('want', 1, 20) as Promise<PaginatedResponse<FavoriteItem>>,
  })

  const doneBooks = useQuery<PaginatedResponse<FavoriteItem>>({
    queryKey: ['library', 'done', 1],
    queryFn: () => api.getLibrary('done', 1, 20) as Promise<PaginatedResponse<FavoriteItem>>,
  })

  const downloads = useQuery<PaginatedResponse<DownloadItem>>({
    queryKey: ['downloads-recent'],
    queryFn: () => api.getDownloads(1) as Promise<PaginatedResponse<DownloadItem>>,
  })

  const progress = useMemo(() => getReadingProgress(), [])

  const recentDownloads = downloads.data?.items?.slice(0, 10) || []
  const currentlyReading = readingBooks.data?.items || []
  const wantToRead = wantBooks.data?.items || []
  const completed = doneBooks.data?.items || []

  const hasAnyContent = currentlyReading.length > 0 || wantToRead.length > 0 || recentDownloads.length > 0 || completed.length > 0

  return (
    <div className="h-full flex flex-col">
      {/* Hero header */}
      <div className="px-5 pt-6 pb-4 page-header-discovery">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <h1
            className="text-[32px] font-bold tracking-tight"
            style={{ color: 'var(--tg-theme-text-color, #000)' }}
          >
            Главная
          </h1>
          <p
            className="text-[14px] mt-0.5"
            style={{ color: 'var(--tg-theme-hint-color, #999)' }}
          >
            Ваша книжная полка
          </p>
        </motion.div>

        {/* Quick actions */}
        <div className="flex gap-2.5 mt-4">
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={() => { selection(); navigate('/search') }}
            className="flex-1 flex items-center gap-2.5 px-4 py-3 rounded-2xl"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 10%, transparent)',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--tg-theme-button-color, #2481cc)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
            <span className="text-[14px] font-semibold" style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}>
              Найти книгу
            </span>
          </motion.button>

          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={() => { selection(); navigate('/audiobooks') }}
            className="flex items-center gap-2.5 px-4 py-3 rounded-2xl"
            style={{
              backgroundColor: 'color-mix(in srgb, #a855f7 10%, transparent)',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#a855f7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 18v-6a9 9 0 0118 0v6" />
              <path d="M21 19a2 2 0 01-2 2h-1a2 2 0 01-2-2v-3a2 2 0 012-2h3zM3 19a2 2 0 002 2h1a2 2 0 002-2v-3a2 2 0 00-2-2H3z" />
            </svg>
            <span className="text-[14px] font-semibold" style={{ color: '#a855f7' }}>
              Аудио
            </span>
          </motion.button>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="page-scroll">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="show"
          className="pt-2"
        >
          {/* Currently Reading */}
          {currentlyReading.length > 0 && (
            <motion.div variants={staggerItem}>
              <HorizontalCarousel
                title="Читаю сейчас"
                icon={
                  <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ backgroundColor: 'rgba(64,192,87,0.12)' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#40C057" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z" />
                      <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z" />
                    </svg>
                  </div>
                }
                onSeeAll={() => navigate('/library')}
              >
                {currentlyReading.map((item) => {
                  const p = progress[item.book_id]
                  return (
                    <BookCoverCard
                      key={item.book_id}
                      id={item.book_id}
                      title={item.title.replace(/\s*\([a-z0-9]+\)\s*$/i, '')}
                      author={item.author}
                      cover={item.cover}
                      progress={p ? Math.round(((p.chapter + 1) * 100) / Math.max(1, 10)) : undefined}
                      badge="Читаю"
                      size="lg"
                    />
                  )
                })}
              </HorizontalCarousel>
            </motion.div>
          )}

          {/* Want to Read */}
          {wantToRead.length > 0 && (
            <motion.div variants={staggerItem}>
              <HorizontalCarousel
                title="Хочу прочитать"
                subtitle={`${wantToRead.length} ${pluralize(wantToRead.length, 'книга', 'книги', 'книг')}`}
                icon={
                  <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ backgroundColor: 'rgba(255,107,107,0.12)' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#FF6B6B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
                    </svg>
                  </div>
                }
                onSeeAll={() => navigate('/library')}
              >
                {wantToRead.slice(0, 15).map((item) => (
                  <BookCoverCard
                    key={item.book_id}
                    id={item.book_id}
                    title={item.title.replace(/\s*\([a-z0-9]+\)\s*$/i, '')}
                    author={item.author}
                    cover={item.cover}
                  />
                ))}
              </HorizontalCarousel>
            </motion.div>
          )}

          {/* Recent Downloads */}
          {recentDownloads.length > 0 && (
            <motion.div variants={staggerItem}>
              <HorizontalCarousel
                title="Недавно скачанные"
                icon={
                  <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ backgroundColor: 'rgba(34,197,94,0.12)' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                      <polyline points="7,10 12,15 17,10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                  </div>
                }
                onSeeAll={() => navigate('/downloads')}
              >
                {recentDownloads.map((item, i) => (
                  <BookCoverCard
                    key={`${item.book_id}-${i}`}
                    id={item.book_id}
                    title={item.title.replace(/\s*\([a-z0-9]+\)\s*$/i, '')}
                    author={item.author}
                    cover={item.cover}
                    badge={item.format.toUpperCase()}
                    size="sm"
                  />
                ))}
              </HorizontalCarousel>
            </motion.div>
          )}

          {/* Completed */}
          {completed.length > 0 && (
            <motion.div variants={staggerItem}>
              <HorizontalCarousel
                title="Прочитано"
                subtitle={`${completed.length} ${pluralize(completed.length, 'книга', 'книги', 'книг')}`}
                icon={
                  <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ backgroundColor: 'rgba(51,154,240,0.12)' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#339AF0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </div>
                }
                onSeeAll={() => navigate('/library')}
              >
                {completed.slice(0, 15).map((item) => (
                  <BookCoverCard
                    key={item.book_id}
                    id={item.book_id}
                    title={item.title.replace(/\s*\([a-z0-9]+\)\s*$/i, '')}
                    author={item.author}
                    cover={item.cover}
                    progress={100}
                    size="sm"
                  />
                ))}
              </HorizontalCarousel>
            </motion.div>
          )}

          {/* Empty state */}
          {!hasAnyContent && !readingBooks.isLoading && !wantBooks.isLoading && !downloads.isLoading && (
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1, type: 'spring', damping: 20, stiffness: 200 }}
              className="flex flex-col items-center justify-center pt-12 px-8"
            >
              <motion.div
                animate={{ y: [0, -6, 0] }}
                transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
                className="relative mb-6"
              >
                <div className="w-[100px] h-[100px] rounded-[28px] flex items-center justify-center"
                  style={{
                    background: 'linear-gradient(135deg, color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 12%, transparent), color-mix(in srgb, #a855f7 8%, transparent))',
                  }}
                >
                  <svg width="44" height="44" viewBox="0 0 24 24" fill="none" style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}>
                    <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
              </motion.div>
              <p
                className="text-[20px] font-bold text-center"
                style={{ color: 'var(--tg-theme-text-color, #000)' }}
              >
                Добро пожаловать!
              </p>
              <p
                className="text-[14px] text-center mt-2 max-w-[280px] leading-relaxed"
                style={{ color: 'var(--tg-theme-hint-color, #999)' }}
              >
                Найдите свою первую книгу через поиск и начните собирать библиотеку
              </p>
              <motion.button
                whileTap={{ scale: 0.95 }}
                onClick={() => navigate('/search')}
                className="mt-6 px-8 py-3.5 rounded-2xl text-[15px] font-semibold"
                style={{
                  backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
                  color: 'var(--tg-theme-button-text-color, #fff)',
                }}
              >
                Начать поиск
              </motion.button>
            </motion.div>
          )}

          {/* Loading state */}
          {(readingBooks.isLoading || wantBooks.isLoading || downloads.isLoading) && !hasAnyContent && (
            <div className="px-5 space-y-6 pt-2">
              {[1, 2, 3].map((section) => (
                <div key={section}>
                  <div className="flex items-center gap-2.5 mb-3">
                    <div className="w-8 h-8 rounded-xl skeleton-shimmer" />
                    <div className="h-5 w-32 rounded-lg skeleton-shimmer" />
                  </div>
                  <div className="flex gap-3">
                    {[1, 2, 3].map((i) => (
                      <div key={i} className="flex-shrink-0">
                        <div className="w-[120px] h-[168px] rounded-xl skeleton-shimmer" />
                        <div className="h-4 w-20 rounded-md skeleton-shimmer mt-2" />
                        <div className="h-3 w-16 rounded-md skeleton-shimmer mt-1" />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </motion.div>
      </div>
    </div>
  )
}

function pluralize(n: number, one: string, few: string, many: string): string {
  const abs = Math.abs(n) % 100
  const lastDigit = abs % 10
  if (abs > 10 && abs < 20) return many
  if (lastDigit > 1 && lastDigit < 5) return few
  if (lastDigit === 1) return one
  return many
}
