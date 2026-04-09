import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
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
      <div className="px-4 pt-4 pb-1">
        <h1 className="text-[34px] font-bold tracking-tight"
          style={{ color: 'var(--tg-theme-text-color, #000)' }}>
          Аудиокниги
        </h1>
      </div>

      {/* Search input */}
      <div className="px-4 py-2">
        <motion.div
          animate={{
            scale: isFocused ? 1.01 : 1,
            boxShadow: isFocused
              ? '0 0 0 2px var(--tg-theme-button-color, #2481cc)'
              : '0 0 0 0px transparent',
          }}
          transition={{ type: 'spring', damping: 20, stiffness: 300 }}
          className="flex items-center gap-2.5 rounded-[14px] px-3.5 py-3"
          style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
            style={{ color: 'var(--tg-theme-hint-color, #999)', flexShrink: 0 }}>
            <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2" />
            <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
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
          {query && (
            <motion.button
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', damping: 15, stiffness: 300 }}
              onClick={() => { setQuery(''); setDebouncedQuery('') }}
              className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: 'var(--tg-theme-hint-color, #999)' }}
            >
              <svg width="8" height="8" viewBox="0 0 10 10" fill="none">
                <path d="M1 1l8 8M9 1l-8 8" stroke="var(--tg-theme-secondary-bg-color, #f0f0f0)" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </motion.button>
          )}
        </motion.div>
      </div>

      {/* Results */}
      <div className="page-scroll">
        {debouncedQuery ? (
          searchResults.isLoading ? (
            <div className="px-4 space-y-3 pt-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="flex gap-3 p-3 rounded-ios-lg skeleton-shimmer h-[72px]"
                  style={{ animationDelay: `${i * 80}ms` }} />
              ))}
            </div>
          ) : !searchResults.data?.items.length ? (
            <EmptyState icon="🎧" title="Ничего не найдено" subtitle={`Нет результатов для «${debouncedQuery}»`} />
          ) : (
            <>
              <p className="px-4 pb-2 text-[13px]" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                Найдено: {searchResults.data.total}
              </p>
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
              <div className="px-4 mt-2">
                <p className="text-[13px] font-semibold uppercase tracking-wider mb-2.5"
                  style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}>
                  Сейчас слушаю
                </p>
                <motion.div variants={staggerContainer} initial="hidden" animate="show">
                  {listeningItems.map((item) => (
                    <motion.div key={item.id} variants={staggerItem}>
                      <motion.button
                        whileTap={{ scale: 0.97 }}
                        onClick={() => {
                          selection()
                          navigate(`/audiobook/${item.topic_id}`)
                        }}
                        className="w-full flex items-center gap-3.5 p-3 rounded-ios-lg text-left"
                        style={{
                          backgroundColor: currentTrack?.topicId === item.topic_id
                            ? 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 8%, transparent)'
                            : 'transparent',
                        }}
                      >
                        <div className="w-[48px] h-[48px] rounded-ios flex-shrink-0 flex items-center justify-center text-xl shadow-sm"
                          style={{ background: 'linear-gradient(135deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 60%, #a855f7))' }}>
                          🎧
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-[14px] font-semibold truncate"
                            style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                            {item.title}
                          </p>
                          <p className="text-[12px] mt-0.5"
                            style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                            Глава {item.current_chapter + 1} из {item.total_chapters}
                          </p>
                          {/* Mini progress bar */}
                          <div className="h-1 rounded-full mt-1.5 overflow-hidden"
                            style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 8%, transparent)' }}>
                            <div className="h-full rounded-full"
                              style={{
                                width: `${item.total_chapters > 0 ? ((item.current_chapter + 1) / item.total_chapters) * 100 : 0}%`,
                                backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
                              }} />
                          </div>
                        </div>
                      </motion.button>
                      <div className="separator mx-4" />
                    </motion.div>
                  ))}
                </motion.div>
              </div>
            )}

            {!listeningItems.length && !progress.isLoading && (
              <EmptyState
                icon="🎧"
                title="Аудиокниги"
                subtitle="Ищите аудиокниги и слушайте прямо здесь"
              />
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
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      onClick={onClick}
      className="w-full flex items-center gap-3.5 px-4 py-3 text-left"
    >
      <div className="w-[48px] h-[48px] rounded-ios flex-shrink-0 flex items-center justify-center text-xl shadow-sm"
        style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}>
        🎵
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[14px] font-semibold leading-tight line-clamp-2"
          style={{ color: 'var(--tg-theme-text-color, #000)' }}>
          {title}
        </p>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-[12px]" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
            {size}
          </span>
          {seeds > 0 && (
            <span className="text-[12px]" style={{ color: seeds > 5 ? '#34c759' : 'var(--tg-theme-hint-color, #999)' }}>
              ● {seeds} сидов
            </span>
          )}
        </div>
      </div>
      <svg width="16" height="16" viewBox="0 0 16 16" style={{ color: 'var(--tg-theme-hint-color, #999)', flexShrink: 0 }}>
        <path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    </motion.button>
  )
}
