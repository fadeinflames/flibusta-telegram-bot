import { useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '../api/client'
import { useBackButton, useHaptic } from '../hooks/useTelegram'
import { useAudioPlayer } from '../contexts/AudioPlayerContext'
import { detailVariants, detailTransition, staggerContainer, staggerItem } from '../lib/animations'
import type { AudiobookTopicInfo, AudiobookFileEntry } from '../api/types'

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

export default function AudiobookDetailPage() {
  const { topicId } = useParams<{ topicId: string }>()
  const navigate = useNavigate()
  const { impact, notification } = useHaptic()
  const { play, currentTrack, isPlaying, toggle } = useAudioPlayer()

  const goBack = useCallback(() => navigate(-1), [navigate])
  useBackButton(goBack)

  const info = useQuery<AudiobookTopicInfo>({
    queryKey: ['audiobook-info', topicId],
    queryFn: () => api.getAudiobookInfo(topicId!) as Promise<AudiobookTopicInfo>,
    enabled: !!topicId,
  })

  const files = useQuery<{ items: AudiobookFileEntry[]; total: number }>({
    queryKey: ['audiobook-files', topicId],
    queryFn: () => api.getAudiobookFiles(topicId!) as Promise<{ items: AudiobookFileEntry[]; total: number }>,
    enabled: !!topicId,
  })

  const audioFiles = files.data?.items || []
  const chapters = audioFiles.map((f, i) => ({
    name: f.filename.replace(/\.[^/.]+$/, ''),
    index: f.index,
  }))

  const titleParts = (info.data?.title || '').split(' - ')
  const author = titleParts.length > 1 ? titleParts[0].trim() : ''
  const bookTitle = titleParts.length > 1 ? titleParts.slice(1).join(' - ').trim() : info.data?.title || ''

  const handlePlayChapter = (fileEntry: AudiobookFileEntry, index: number) => {
    impact('medium')
    play(
      {
        topicId: topicId!,
        fileIndex: fileEntry.index,
        title: bookTitle,
        author,
        chapterName: fileEntry.filename.replace(/\.[^/.]+$/, ''),
      },
      chapters,
    )
  }

  const handleDownload = async () => {
    impact('medium')
    try {
      await api.enqueueAudiobookDownload(topicId!)
      notification('success')
    } catch {
      notification('error')
    }
  }

  const isCurrentBook = currentTrack?.topicId === topicId

  if (info.isLoading) {
    return (
      <motion.div
        variants={detailVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={detailTransition}
        className="h-full"
        style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}
      >
        <div className="page-scroll">
          <div className="h-[240px] skeleton-shimmer" />
          <div className="p-5 space-y-3">
            <div className="h-7 w-3/4 rounded-2xl skeleton-shimmer mx-auto" />
            <div className="h-5 w-1/2 rounded-2xl skeleton-shimmer mx-auto" />
            <div className="h-14 w-full rounded-2xl skeleton-shimmer mt-4" />
          </div>
        </div>
      </motion.div>
    )
  }

  return (
    <motion.div
      variants={detailVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={detailTransition}
      className="h-full"
      style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}
    >
      <div className="page-scroll" style={{ paddingBottom: '32px' }}>
        {/* Rich gradient hero */}
        <div
          className="relative h-[240px] flex items-end justify-center overflow-hidden"
          style={{
            background: 'linear-gradient(145deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 40%, #7c3aed))',
          }}
        >
          {/* Decorative circles */}
          <div
            className="absolute top-[-40px] right-[-40px] w-[160px] h-[160px] rounded-full"
            style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}
          />
          <div
            className="absolute bottom-[-20px] left-[-20px] w-[100px] h-[100px] rounded-full"
            style={{ backgroundColor: 'rgba(255,255,255,0.04)' }}
          />

          {/* Frosted back button */}
          <button
            onClick={goBack}
            className="absolute top-4 left-4 z-20 w-10 h-10 rounded-full flex items-center justify-center"
            style={{
              backgroundColor: 'rgba(255,255,255,0.18)',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              border: '1px solid rgba(255,255,255,0.2)',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>

          {/* Large audiobook icon */}
          <motion.div
            initial={{ scale: 0.75, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', damping: 20, stiffness: 180, delay: 0.1 }}
            className="relative z-10 pb-6"
          >
            <div
              className="w-[130px] h-[130px] rounded-[28px] flex items-center justify-center"
              style={{
                backgroundColor: 'rgba(255,255,255,0.12)',
                backdropFilter: 'blur(16px)',
                WebkitBackdropFilter: 'blur(16px)',
                border: '1px solid rgba(255,255,255,0.15)',
                boxShadow: '0 16px 48px rgba(0,0,0,0.2)',
              }}
            >
              <span className="text-[60px]">🎧</span>
            </div>
          </motion.div>
        </div>

        {/* Title and author */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.2 }}
          className="px-5 pt-5"
        >
          <h1
            className="text-[22px] font-bold leading-tight text-center tracking-tight"
            style={{ color: 'var(--tg-theme-text-color, #000)' }}
          >
            {bookTitle}
          </h1>
          {author && (
            <p
              className="text-[16px] text-center mt-1.5 font-medium"
              style={{ color: 'var(--tg-theme-link-color, #2481cc)' }}
            >
              {author}
            </p>
          )}
        </motion.div>

        {/* Large centered play button */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.3 }}
          className="flex flex-col items-center gap-3 px-5 mt-6"
        >
          {audioFiles.length > 0 && (
            <motion.button
              whileTap={{ scale: 0.94 }}
              onClick={() => {
                if (isCurrentBook) {
                  toggle()
                } else if (audioFiles.length > 0) {
                  handlePlayChapter(audioFiles[0], 0)
                }
              }}
              className="w-full flex items-center justify-center gap-3 py-4 rounded-2xl text-[17px] font-bold"
              style={{
                background: 'linear-gradient(135deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 70%, #7c3aed))',
                color: 'var(--tg-theme-button-text-color, #fff)',
                boxShadow: '0 8px 24px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 40%, transparent)',
              }}
            >
              {isCurrentBook && isPlaying ? (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="4" width="4" height="16" rx="1" />
                  <rect x="14" y="4" width="4" height="16" rx="1" />
                </svg>
              ) : (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
              )}
              {isCurrentBook && isPlaying ? 'Пауза' : 'Слушать'}
            </motion.button>
          )}

          {/* Download button */}
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={handleDownload}
            className="w-full flex items-center justify-center gap-2.5 py-3.5 rounded-2xl text-[15px] font-semibold"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
              color: 'var(--tg-theme-text-color, #000)',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="7,10 12,15 17,10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Скачать
          </motion.button>
        </motion.div>

        {/* Description */}
        {info.data?.description && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.35 }}
            className="px-5 mt-6"
          >
            <p
              className="text-[13px] font-semibold uppercase tracking-wider mb-3"
              style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}
            >
              Описание
            </p>
            <div
              className="p-4 rounded-2xl"
              style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
            >
              <p
                className="text-[14px] leading-[1.65]"
                style={{ color: 'var(--tg-theme-text-color, #000)' }}
              >
                {info.data.description}
              </p>
            </div>
          </motion.div>
        )}

        {/* Chapter list */}
        {audioFiles.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.4 }}
            className="mt-6"
          >
            <p
              className="px-5 text-[13px] font-semibold uppercase tracking-wider mb-3"
              style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}
            >
              Главы ({audioFiles.length})
            </p>
            <div
              className="mx-5 rounded-2xl overflow-hidden"
              style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
            >
              <motion.div variants={staggerContainer} initial="hidden" animate="show">
                {audioFiles.map((file, i) => {
                  const isCurrent = isCurrentBook && currentTrack?.fileIndex === file.index
                  const isLast = i === audioFiles.length - 1
                  return (
                    <motion.div key={file.index} variants={staggerItem}>
                      <motion.button
                        whileTap={{ scale: 0.98 }}
                        onClick={() => handlePlayChapter(file, i)}
                        className="w-full flex items-center gap-3.5 px-4 py-3.5 text-left relative"
                        style={{
                          backgroundColor: isCurrent
                            ? 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 10%, transparent)'
                            : 'transparent',
                        }}
                      >
                        {/* Numbered indicator */}
                        <div
                          className="w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center text-[13px] font-bold relative"
                          style={{
                            backgroundColor: isCurrent
                              ? 'var(--tg-theme-button-color, #2481cc)'
                              : 'color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)',
                            color: isCurrent
                              ? 'var(--tg-theme-button-text-color, #fff)'
                              : 'var(--tg-theme-hint-color, #999)',
                          }}
                        >
                          {isCurrent && isPlaying ? (
                            <motion.div
                              className="flex items-end gap-[2px] h-[14px]"
                              aria-label="Playing"
                            >
                              {[0, 1, 2].map(bar => (
                                <motion.div
                                  key={bar}
                                  className="w-[3px] rounded-full"
                                  style={{ backgroundColor: 'var(--tg-theme-button-text-color, #fff)' }}
                                  animate={{ height: ['4px', '14px', '4px'] }}
                                  transition={{
                                    duration: 0.8,
                                    repeat: Infinity,
                                    delay: bar * 0.15,
                                    ease: 'easeInOut',
                                  }}
                                />
                              ))}
                            </motion.div>
                          ) : (
                            i + 1
                          )}
                        </div>

                        {/* Chapter info */}
                        <div className="flex-1 min-w-0">
                          <p
                            className="text-[15px] font-medium truncate"
                            style={{
                              color: isCurrent
                                ? 'var(--tg-theme-button-color, #2481cc)'
                                : 'var(--tg-theme-text-color, #000)',
                            }}
                          >
                            {file.filename.replace(/\.[^/.]+$/, '')}
                          </p>
                          <p
                            className="text-[12px] mt-0.5 font-medium"
                            style={{ color: 'var(--tg-theme-hint-color, #999)' }}
                          >
                            {formatFileSize(file.size_bytes)}
                          </p>
                        </div>

                        {/* Play indicator for current */}
                        {isCurrent && (
                          <div style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                              <polygon points="5 3 19 12 5 21 5 3" />
                            </svg>
                          </div>
                        )}
                      </motion.button>
                      {!isLast && (
                        <div
                          className="h-px ml-[60px] mr-4"
                          style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)' }}
                        />
                      )}
                    </motion.div>
                  )
                })}
              </motion.div>
            </div>
          </motion.div>
        )}

        {/* Empty state */}
        {!files.isLoading && audioFiles.length === 0 && (
          <div className="px-5 mt-10 text-center">
            <div className="text-[48px] mb-3 opacity-30">📂</div>
            <p className="text-[16px] font-semibold" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
              Файлы ещё не загружены
            </p>
            <p className="text-[14px] mt-1.5" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
              Нажмите кнопку загрузки, чтобы начать скачивание
            </p>
          </div>
        )}
      </div>
    </motion.div>
  )
}
