import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '../api/client'
import { useHaptic } from '../hooks/useTelegram'
import type { PaginatedResponse, BookBrief, SearchHistoryItem } from '../api/types'
import { staggerContainer, staggerItem } from '../lib/animations'
import BookCard from '../components/books/BookCard'
import SkeletonCard from '../components/books/SkeletonCard'
import EmptyState from '../components/ui/EmptyState'

type SearchType = 'title' | 'author'

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

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-5 pt-5 pb-1">
        <h1 className="text-[28px] font-bold tracking-tight" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
          Поиск
        </h1>
      </div>

      {/* Search input */}
      <div className="px-4 py-2.5">
        <div
          className="flex items-center gap-2.5 rounded-2xl px-4 py-3 transition-all duration-200"
          style={{
            backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
            boxShadow: isFocused
              ? '0 0 0 2px var(--tg-theme-button-color, #2481cc), 0 4px 16px rgba(0,0,0,0.08)'
              : '0 1px 3px rgba(0,0,0,0.04)',
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" style={{ color: 'var(--tg-theme-hint-color, #999)', flexShrink: 0 }}>
            <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2" />
            <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
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
          {query && (
            <motion.button
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ duration: 0.15 }}
              onClick={() => { setQuery(''); setDebouncedQuery('') }}
              className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: 'var(--tg-theme-hint-color, #999)' }}
            >
              <svg width="8" height="8" viewBox="0 0 10 10" fill="none">
                <path d="M1 1l8 8M9 1l-8 8" stroke="var(--tg-theme-secondary-bg-color, #f0f0f0)" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </motion.button>
          )}
        </div>
      </div>

      {/* Search type toggle */}
      <div className="flex gap-2 px-4 pb-3">
        {(['title', 'author'] as SearchType[]).map(type => {
          const isActive = searchType === type
          const label = type === 'title' ? 'По названию' : 'По автору'
          return (
            <button
              key={type}
              onClick={() => { selection(); setSearchType(type); setPage(1); if (debouncedQuery) setDebouncedQuery(query.trim()) }}
              className="px-4 py-2 rounded-xl text-[13px] font-semibold transition-all duration-200"
              style={{
                color: isActive ? 'var(--tg-theme-button-text-color, #fff)' : 'var(--tg-theme-text-color, #000)',
                backgroundColor: isActive
                  ? 'var(--tg-theme-button-color, #2481cc)'
                  : 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
              }}
            >
              {label}
            </button>
          )
        })}
      </div>

      {/* Results */}
      <div className="page-scroll">
        {debouncedQuery ? (
          (searchResults.isLoading || searchResults.isFetching) ? (
            <div className="px-1">{[...Array(5)].map((_, i) => <SkeletonCard key={i} delay={i * 60} />)}</div>
          ) : searchResults.isError ? (
            <EmptyState icon="⚠️" title="Ошибка поиска" subtitle="Не удалось выполнить поиск. Попробуйте ещё раз." />
          ) : !searchResults.data || searchResults.data.items.length === 0 ? (
            <EmptyState icon="🔍" title="Ничего не найдено" subtitle={`По запросу «${debouncedQuery}» результатов нет`} />
          ) : (
            <>
              <p className="px-5 pb-2 text-[13px] font-medium" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                Найдено: {searchResults.data.total}
              </p>
              <motion.div variants={staggerContainer} initial="hidden" animate="show">
                {searchResults.data.items.map((book: BookBrief) => (
                  <motion.div key={book.id} variants={staggerItem}>
                    <BookCard id={book.id} title={book.title} author={book.author} cover={book.cover} />
                    <div className="separator mx-4" />
                  </motion.div>
                ))}
              </motion.div>
              {totalPages > 1 && (
                <div className="flex justify-center items-center gap-3 py-5">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
                    className="px-4 py-2 rounded-xl text-[13px] font-semibold disabled:opacity-20 transition-opacity"
                    style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-text-color)' }}>
                    Назад
                  </button>
                  <span className="text-[13px] font-medium tabular-nums" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {page} / {totalPages}
                  </span>
                  <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                    className="px-4 py-2 rounded-xl text-[13px] font-semibold disabled:opacity-20 transition-opacity"
                    style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-text-color)' }}>
                    Далее
                  </button>
                </div>
              )}
            </>
          )
        ) : (
          <>
            {/* Search history */}
            {history.data?.items && history.data.items.length > 0 && (
              <div className="px-5 mt-2">
                <p className="text-[13px] font-semibold mb-3 uppercase tracking-wider"
                  style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}>
                  Недавние запросы
                </p>
                <div className="flex flex-wrap gap-2">
                  {history.data.items.slice(0, 10).map((h: SearchHistoryItem, i: number) => (
                    <button
                      key={i}
                      onClick={() => { selection(); setQuery(h.query); setDebouncedQuery(h.query) }}
                      className="px-3.5 py-2 rounded-xl text-[13px] font-medium transition-transform active:scale-95"
                      style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)', color: 'var(--tg-theme-text-color, #000)' }}
                    >
                      {h.query}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Quick start hint */}
            {(!history.data?.items || history.data.items.length === 0) && (
              <div className="flex flex-col items-center justify-center pt-20 px-8">
                <div className="text-[48px] mb-4 opacity-60">📖</div>
                <p className="text-[16px] font-semibold text-center" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                  Найдите свою книгу
                </p>
                <p className="text-[14px] text-center mt-1.5 max-w-[260px]" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                  Введите название книги или имя автора для поиска
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
