import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../api/client'
import { useHaptic } from '../hooks/useTelegram'
import type { PaginatedResponse, BookBrief, SearchHistoryItem } from '../api/types'
import { staggerContainer, staggerItem } from '../lib/animations'
import BookCard from '../components/books/BookCard'
import SkeletonCard from '../components/books/SkeletonCard'
import EmptyState from '../components/ui/EmptyState'

type SearchType = 'title' | 'author'

const SEARCH_TYPES: { key: SearchType; label: string }[] = [
  { key: 'title', label: 'По названию' },
  { key: 'author', label: 'По автору' },
]

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [searchType, setSearchType] = useState<SearchType>('title')
  const [isFocused, setIsFocused] = useState(false)
  const [page, setPage] = useState(1)
  const inputRef = useRef<HTMLInputElement>(null)
  const { selection } = useHaptic()
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  const handleQueryChange = useCallback((value: string) => {
    setQuery(value)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      setDebouncedQuery(value.trim())
      setPage(1)
    }, 400)
  }, [])

  useEffect(() => () => clearTimeout(timerRef.current), [])

  const searchResults = useQuery<PaginatedResponse<BookBrief>>({
    queryKey: ['search', debouncedQuery, searchType, page],
    queryFn: () => api.searchBooks(debouncedQuery, searchType, page) as Promise<PaginatedResponse<BookBrief>>,
    enabled: debouncedQuery.length >= 2,
  })

  const history = useQuery<PaginatedResponse<SearchHistoryItem>>({
    queryKey: ['search-history'],
    queryFn: () => api.getSearchHistory() as Promise<PaginatedResponse<SearchHistoryItem>>,
    enabled: !debouncedQuery,
  })

  const totalPages = searchResults.data ? Math.ceil(searchResults.data.total / searchResults.data.per_page) : 0

  const activeIndex = SEARCH_TYPES.findIndex(t => t.key === searchType)

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-5 pt-6 pb-2 page-header-search">
        <h1
          className="text-[32px] font-bold tracking-tight"
          style={{ color: 'var(--tg-theme-text-color, #000)' }}
        >
          Поиск
        </h1>
        <p
          className="text-[14px] mt-0.5"
          style={{ color: 'var(--tg-theme-hint-color, #999)' }}
        >
          Книги, авторы и серии
        </p>
      </div>

      {/* Search input */}
      <div className="px-4 pt-2 pb-2.5">
        <motion.div
          animate={{
            boxShadow: isFocused
              ? '0 0 0 2px var(--tg-theme-button-color, #2481cc), 0 4px 20px rgba(0,0,0,0.06)'
              : '0 0 0 0px transparent, 0 1px 4px rgba(0,0,0,0.04)',
          }}
          transition={{ type: 'spring', damping: 25, stiffness: 400 }}
          className="flex items-center gap-3 rounded-2xl px-4 py-3.5"
          style={{
            backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
          }}
        >
          <motion.svg
            animate={{
              color: isFocused ? 'var(--tg-theme-button-color, #2481cc)' : 'var(--tg-theme-hint-color, #999)',
            }}
            width="20" height="20" viewBox="0 0 24 24" fill="none"
            style={{ flexShrink: 0 }}
          >
            <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2" />
            <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </motion.svg>
          <input
            ref={inputRef}
            type="text"
            placeholder="Название книги или автор..."
            value={query}
            onChange={e => handleQueryChange(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            className="flex-1 bg-transparent text-[15px] outline-none placeholder:opacity-40"
            style={{ color: 'var(--tg-theme-text-color, #000)' }}
          />
          <AnimatePresence>
            {query && (
              <motion.button
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0, opacity: 0 }}
                transition={{ type: 'spring', damping: 20, stiffness: 400 }}
                onClick={() => { setQuery(''); setDebouncedQuery('') }}
                className="w-[22px] h-[22px] rounded-full flex items-center justify-center flex-shrink-0"
                style={{ backgroundColor: 'var(--tg-theme-hint-color, #999)' }}
              >
                <svg width="8" height="8" viewBox="0 0 10 10" fill="none">
                  <path d="M1 1l8 8M9 1l-8 8" stroke="var(--tg-theme-secondary-bg-color, #f0f0f0)" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </motion.button>
            )}
          </AnimatePresence>
        </motion.div>
      </div>

      {/* Search type toggle -- iOS segmented control */}
      <div className="px-4 pb-3">
        <div
          className="relative flex p-[3px] rounded-[14px]"
          style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
        >
          {/* Animated sliding indicator */}
          <motion.div
            className="absolute top-[3px] bottom-[3px] rounded-[11px]"
            style={{
              width: `calc(${100 / SEARCH_TYPES.length}% - 3px)`,
              backgroundColor: 'var(--tg-theme-bg-color, #fff)',
              boxShadow: '0 1px 4px rgba(0,0,0,0.08), 0 0.5px 1px rgba(0,0,0,0.04)',
            }}
            animate={{ left: `calc(${activeIndex * (100 / SEARCH_TYPES.length)}% + 1.5px)` }}
            transition={{ type: 'spring', damping: 28, stiffness: 380 }}
          />
          {SEARCH_TYPES.map(type => {
            const isActive = searchType === type.key
            return (
              <button
                key={type.key}
                onClick={() => {
                  selection()
                  setSearchType(type.key)
                  setPage(1)
                  if (debouncedQuery) setDebouncedQuery(query.trim())
                }}
                className="relative flex-1 py-2 text-[13px] font-semibold text-center z-10 transition-colors duration-200"
                style={{
                  color: isActive
                    ? 'var(--tg-theme-text-color, #000)'
                    : 'var(--tg-theme-hint-color, #999)',
                }}
              >
                {type.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Results area */}
      <div className="page-scroll">
        {debouncedQuery ? (
          (searchResults.isLoading || searchResults.isFetching) ? (
            <div className="px-1">
              {[...Array(5)].map((_, i) => <SkeletonCard key={i} delay={i * 60} />)}
            </div>
          ) : searchResults.isError ? (
            <EmptyState
              icon="⚠️"
              title="Ошибка поиска"
              subtitle="Не удалось выполнить поиск. Попробуйте ещё раз."
            />
          ) : !searchResults.data || searchResults.data.items.length === 0 ? (
            <EmptyState
              icon="🔍"
              title="Ничего не найдено"
              subtitle={`По запросу «${debouncedQuery}» результатов нет`}
            />
          ) : (
            <>
              {/* Results count */}
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="px-5 pb-2 text-[13px] font-medium"
                style={{ color: 'var(--tg-theme-hint-color, #999)' }}
              >
                Найдено: {searchResults.data.total}
              </motion.p>

              {/* Results list */}
              <motion.div variants={staggerContainer} initial="hidden" animate="show">
                {searchResults.data.items.map((book: BookBrief) => (
                  <motion.div key={book.id} variants={staggerItem}>
                    <BookCard id={book.id} title={book.title} author={book.author} cover={book.cover} />
                    <div className="separator mx-4" />
                  </motion.div>
                ))}
              </motion.div>

              {/* Pagination */}
              {totalPages > 1 && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 }}
                  className="flex justify-center items-center gap-4 py-6"
                >
                  <motion.button
                    whileTap={{ scale: 0.95 }}
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="w-10 h-10 rounded-full flex items-center justify-center disabled:opacity-20 transition-all"
                    style={{
                      backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                      color: 'var(--tg-theme-text-color)',
                    }}
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <path d="M10 3L5 8l5 5" />
                    </svg>
                  </motion.button>

                  <div className="flex items-center gap-1.5">
                    <span
                      className="text-[15px] font-bold tabular-nums"
                      style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}
                    >
                      {page}
                    </span>
                    <span className="text-[13px]" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                      /
                    </span>
                    <span className="text-[13px] tabular-nums" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                      {totalPages}
                    </span>
                  </div>

                  <motion.button
                    whileTap={{ scale: 0.95 }}
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="w-10 h-10 rounded-full flex items-center justify-center disabled:opacity-20 transition-all"
                    style={{
                      backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                      color: 'var(--tg-theme-text-color)',
                    }}
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <path d="M6 3l5 5-5 5" />
                    </svg>
                  </motion.button>
                </motion.div>
              )}
            </>
          )
        ) : (
          <>
            {/* Search history chips */}
            {history.data?.items && history.data.items.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 }}
                className="px-5 mt-3"
              >
                <div className="flex items-center gap-2 mb-3">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                    style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M12 7v5l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                  <p
                    className="text-[13px] font-semibold uppercase tracking-wider"
                    style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}
                  >
                    Недавние запросы
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {history.data.items.slice(0, 10).map((h: SearchHistoryItem, i: number) => (
                    <motion.button
                      key={i}
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: i * 0.03 }}
                      whileTap={{ scale: 0.93 }}
                      onClick={() => { selection(); setQuery(h.query); setDebouncedQuery(h.query) }}
                      className="px-3.5 py-2 rounded-xl text-[13px] font-medium glass-border"
                      style={{
                        backgroundColor: 'color-mix(in srgb, var(--tg-theme-secondary-bg-color, #f0f0f0) 80%, var(--tg-theme-button-color, #2481cc) 5%)',
                        color: 'var(--tg-theme-text-color, #000)',
                      }}
                    >
                      {h.query}
                    </motion.button>
                  ))}
                </div>
              </motion.div>
            )}

            {/* Empty state -- no history */}
            {(!history.data?.items || history.data.items.length === 0) && (
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1, type: 'spring', damping: 20, stiffness: 200 }}
                className="flex flex-col items-center justify-center pt-16 px-8"
              >
                {/* Decorative icon cluster */}
                <div className="relative mb-6">
                  <motion.div
                    animate={{ y: [0, -5, 0] }}
                    transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
                    className="w-[80px] h-[80px] rounded-[22px] flex items-center justify-center"
                    style={{
                      background: 'linear-gradient(135deg, color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 15%, transparent), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 8%, transparent))',
                    }}
                  >
                    <svg width="36" height="36" viewBox="0 0 24 24" fill="none"
                      style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}>
                      <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                  </motion.div>
                </div>
                <p
                  className="text-[18px] font-bold text-center"
                  style={{ color: 'var(--tg-theme-text-color, #000)' }}
                >
                  Найдите свою книгу
                </p>
                <p
                  className="text-[14px] text-center mt-2 max-w-[260px] leading-relaxed"
                  style={{ color: 'var(--tg-theme-hint-color, #999)' }}
                >
                  Введите название или имя автора, и мы найдем нужное издание
                </p>
              </motion.div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
