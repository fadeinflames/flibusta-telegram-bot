import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../api/client'
import { useHaptic } from '../hooks/useTelegram'
import { useAudioPlayer } from '../contexts/AudioPlayerContext'
import { pageVariants, pageTransition, staggerContainer, staggerItem } from '../lib/animations'
import type { AudiobookSearchResult, ListeningProgressItem } from '../api/types'
import EmptyState from '../components/ui/EmptyState'

export default function AudiobooksPage() {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()
  const { selection } = useHaptic()
  const navigate = useNavigate()
  const { currentTrack } = useAudioPlayer()

  const handleQueryChange = useCallback((value: string) => {
    setQuery(value)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      setDebouncedQuery(value.trim())
    }, 400)
  }, [])

  useEffect(() => () => clearTimeout(timerRef.current), [])

  const searchResults = useQuery<{ items: AudiobookSearchResult[]; total: number }>({
    queryKey: ['audiobook-search', debouncedQuery],
    queryFn: () => api.searchAudiobooks(debouncedQuery) as Promise<{ items: AudiobookSearchResult[]; total: number }>,
    enabled: debouncedQuery.length >= 2,
  })

  const progress = useQuery<{ items: ListeningProgressItem[] }>({
    queryKey: ['listening-progress'],
    queryFn: () => api.getListeningProgress() as Promise<{ items: ListeningProgressItem[] }>,
    enabled: !debouncedQuery,
  })

  const listeningItems = progress.data?.items || []

  return (
    <motion.div
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={pageTransition}
      className="h-full flex flex-col"
    >
      {/* Header */}
      <div className="relative px-5 pt-6 pb-2">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'linear-gradient(180deg, color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 6%, transparent) 0%, transparent 100%)',
          }}
        />
        <h1
          className="relative text-[32px] font-bold tracking-tight"
          style={{ color: 'var(--tg-theme-text-color, #000)' }}
        >
          Аудиокниги
        </h1>
        <p
          className="relative text-[14px] mt-0.5"
          style={{ color: 'var(--tg-theme-hint-color, #999)' }}
        >
          Слушайте книги онлайн
        </p>
      </div>

      {/* Search input */}
      <div className="px-4 pt-2 pb-3">
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
            placeholder="Поиск аудиокниг..."
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

      {/* Results */}
      <div className="page-scroll">
        {debouncedQuery ? (
          searchResults.isLoading ? (
            <div className="px-4 space-y-2 pt-1">
              {[...Array(5)].map((_, i) => (
                <div
                  key={i}
                  className="flex gap-3.5 p-3 rounded-2xl skeleton-shimmer h-[76px]"
                  style={{ animationDelay: `${i * 80}ms` }}
                />
              ))}
            </div>
          ) : !searchResults.data?.items.length ? (
            <EmptyState icon="🎧" title="Ничего не найдено" subtitle={`Нет результатов для «${debouncedQuery}»`} />
          ) : (
            <>
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="px-5 pb-2 text-[13px] font-medium"
                style={{ color: 'var(--tg-theme-hint-color, #999)' }}
              >
                Найдено: {searchResults.data.total}
              </motion.p>
              <motion.div variants={staggerContainer} initial="hidden" animate="show">
                {searchResults.data.items.map((item) => (
                  <motion.div key={item.topic_id} variants={staggerItem}>
                    <AudiobookRow
                      topicId={item.topic_id}
                      title={item.title}
                      size={item.size}
                      seeds={item.seeds}
                      onClick={() => {
                        selection()
                        navigate(`/audiobook/${item.topic_id}`)
                      }}
                    />
                    <div className="separator mx-4" />
                  </motion.div>
                ))}
              </motion.div>
            </>
          )
        ) : (
          <>
            {/* Currently listening */}
            {listeningItems.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 }}
                className="px-4 mt-2"
              >
                <div className="flex items-center gap-2 mb-3">
                  <div
                    className="w-5 h-5 rounded-full flex items-center justify-center"
                    style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 15%, transparent)' }}
                  >
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none"
                      style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}>
                      <path d="M2 1l6 4-6 4V1z" fill="currentColor" />
                    </svg>
                  </div>
                  <p
                    className="text-[13px] font-semibold uppercase tracking-wider"
                    style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}
                  >
                    Сейчас слушаю
                  </p>
                </div>
                <motion.div
                  variants={staggerContainer}
                  initial="hidden"
                  animate="show"
                  className="space-y-1.5"
                >
                  {listeningItems.map((item) => {
                    const progressPercent = item.total_chapters > 0
                      ? ((item.current_chapter + 1) / item.total_chapters) * 100
                      : 0
                    const isActive = currentTrack?.topicId === item.topic_id

                    return (
                      <motion.div key={item.id} variants={staggerItem}>
                        <motion.button
                          whileTap={{ scale: 0.97 }}
                          onClick={() => {
                            selection()
                            navigate(`/audiobook/${item.topic_id}`)
                          }}
                          className="w-full flex items-center gap-3.5 p-3 rounded-2xl text-left transition-colors"
                          style={{
                            backgroundColor: isActive
                              ? 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 8%, transparent)'
                              : 'color-mix(in srgb, var(--tg-theme-secondary-bg-color, #f0f0f0) 60%, transparent)',
                          }}
                        >
                          {/* Album art / cover */}
                          <div
                            className="w-[52px] h-[52px] rounded-[14px] flex-shrink-0 flex items-center justify-center shadow-sm relative overflow-hidden"
                            style={{
                              background: item.cover
                                ? undefined
                                : isActive
                                  ? 'linear-gradient(135deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 60%, #a855f7))'
                                  : 'linear-gradient(135deg, color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 70%, #6366f1), var(--tg-theme-button-color, #2481cc))',
                            }}
                          >
                            {item.cover ? (
                              <img src={item.cover} alt="" className="w-full h-full object-cover" loading="lazy" />
                            ) : (
                              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.9 }}>
                                <path d="M3 18v-6a9 9 0 0118 0v6" />
                                <path d="M21 19a2 2 0 01-2 2h-1a2 2 0 01-2-2v-3a2 2 0 012-2h3v5zM3 19a2 2 0 002 2h1a2 2 0 002-2v-3a2 2 0 00-2-2H3v5z" />
                              </svg>
                            )}
                          </div>

                          <div className="flex-1 min-w-0">
                            <p
                              className="text-[14px] font-semibold truncate leading-tight"
                              style={{ color: 'var(--tg-theme-text-color, #000)' }}
                            >
                              {item.title}
                            </p>
                            <p
                              className="text-[12px] mt-0.5"
                              style={{ color: 'var(--tg-theme-hint-color, #999)' }}
                            >
                              Глава {item.current_chapter + 1} из {item.total_chapters}
                            </p>
                            {/* Progress bar */}
                            <div
                              className="h-[3px] rounded-full mt-2 overflow-hidden"
                              style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 8%, transparent)' }}
                            >
                              <motion.div
                                className="h-full rounded-full"
                                initial={{ width: 0 }}
                                animate={{ width: `${progressPercent}%` }}
                                transition={{ duration: 0.8, ease: 'easeOut', delay: 0.2 }}
                                style={{
                                  backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
                                }}
                              />
                            </div>
                          </div>

                          {/* Chevron */}
                          <svg
                            width="16" height="16" viewBox="0 0 16 16" fill="none"
                            style={{ color: 'var(--tg-theme-hint-color, #999)', flexShrink: 0, opacity: 0.5 }}
                          >
                            <path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        </motion.button>
                      </motion.div>
                    )
                  })}
                </motion.div>
              </motion.div>
            )}

            {/* Empty state */}
            {!listeningItems.length && !progress.isLoading && (
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1, type: 'spring', damping: 20, stiffness: 200 }}
                className="flex flex-col items-center justify-center pt-16 px-8"
              >
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
                      <path d="M3 18v-6a9 9 0 0118 0v6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                      <path d="M21 19a2 2 0 01-2 2h-1a2 2 0 01-2-2v-3a2 2 0 012-2h3v5zM3 19a2 2 0 002 2h1a2 2 0 002-2v-3a2 2 0 00-2-2H3v5z" stroke="currentColor" strokeWidth="1.5" />
                    </svg>
                  </motion.div>
                </div>
                <p
                  className="text-[18px] font-bold text-center"
                  style={{ color: 'var(--tg-theme-text-color, #000)' }}
                >
                  Откройте мир аудиокниг
                </p>
                <p
                  className="text-[14px] text-center mt-2 max-w-[260px] leading-relaxed"
                  style={{ color: 'var(--tg-theme-hint-color, #999)' }}
                >
                  Найдите любимые книги и слушайте их прямо в приложении
                </p>
              </motion.div>
            )}
          </>
        )}
      </div>
    </motion.div>
  )
}

function AudiobookRow({ topicId, title, size, seeds, onClick }: {
  topicId: string
  title: string
  size: string
  seeds: number
  onClick: () => void
}) {
  const seedColor = seeds >= 10 ? '#34c759' : seeds >= 3 ? '#ff9f0a' : 'var(--tg-theme-hint-color, #999)'

  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      onClick={onClick}
      className="w-full flex items-center gap-3.5 px-4 py-3.5 text-left"
    >
      {/* Gradient accent icon */}
      <div
        className="w-[48px] h-[48px] rounded-[13px] flex-shrink-0 flex items-center justify-center shadow-sm"
        style={{
          background: 'linear-gradient(135deg, color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 20%, transparent), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 10%, transparent))',
        }}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
          style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}>
          <path d="M9 18V5l12-2v13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="6" cy="18" r="3" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="18" cy="16" r="3" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </div>

      <div className="flex-1 min-w-0">
        <p
          className="text-[14px] font-semibold leading-tight line-clamp-2"
          style={{ color: 'var(--tg-theme-text-color, #000)' }}
        >
          {title}
        </p>
        <div className="flex items-center gap-2.5 mt-1.5">
          <span
            className="text-[12px]"
            style={{ color: 'var(--tg-theme-hint-color, #999)' }}
          >
            {size}
          </span>
          {seeds > 0 && (
            <span className="flex items-center gap-1 text-[12px]" style={{ color: seedColor }}>
              <span
                className="w-[6px] h-[6px] rounded-full inline-block"
                style={{ backgroundColor: seedColor }}
              />
              {seeds}
            </span>
          )}
        </div>
      </div>

      <svg
        width="16" height="16" viewBox="0 0 16 16" fill="none"
        style={{ color: 'var(--tg-theme-hint-color, #999)', flexShrink: 0, opacity: 0.5 }}
      >
        <path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </motion.button>
  )
}
