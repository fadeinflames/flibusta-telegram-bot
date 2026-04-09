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

  // Extract author from title (format: "Author - Title")
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
          <div className="h-[200px] skeleton-shimmer" />
          <div className="p-4 space-y-3">
            <div className="h-6 w-3/4 rounded-ios skeleton-shimmer" />
            <div className="h-4 w-1/2 rounded-ios skeleton-shimmer" />
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
      <div className="page-scroll" style={{ paddingBottom: '24px' }}>
        {/* Hero */}
        <div className="relative h-[200px] flex items-end justify-center overflow-hidden"
          style={{
            background: 'linear-gradient(135deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 60%, #a855f7))',
          }}>
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', damping: 20, stiffness: 200, delay: 0.15 }}
            className="relative z-10 pb-5"
          >
            <div className="w-[120px] h-[120px] rounded-[20px] flex items-center justify-center shadow-float bg-white/10 backdrop-blur-sm">
              <span className="text-[56px]">🎧</span>
            </div>
          </motion.div>
        </div>

        {/* Info */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.2 }}
          className="px-4 pt-4"
        >
          <h1 className="text-[20px] font-bold leading-tight text-center"
            style={{ color: 'var(--tg-theme-text-color, #000)' }}>
            {bookTitle}
          </h1>
          {author && (
            <p className="text-[15px] text-center mt-1"
              style={{ color: 'var(--tg-theme-link-color, #2481cc)' }}>
              {author}
            </p>
          )}
        </motion.div>

        {/* Action buttons */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.3 }}
          className="flex gap-3 px-4 mt-4"
        >
          {audioFiles.length > 0 && (
            <motion.button
              whileTap={{ scale: 0.96 }}
              onClick={() => {
                if (currentTrack?.topicId === topicId) {
                  toggle()
                } else if (audioFiles.length > 0) {
                  handlePlayChapter(audioFiles[0], 0)
                }
              }}
              className="flex-1 flex items-center justify-center gap-2 py-3 rounded-ios-lg text-[15px] font-semibold shadow-sm"
              style={{
                backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
                color: 'var(--tg-theme-button-text-color, #fff)',
              }}
            >
              {currentTrack?.topicId === topicId && isPlaying ? '⏸ Пауза' : '▶ Слушать'}
            </motion.button>
          )}
          <motion.button
            whileTap={{ scale: 0.93 }}
            onClick={handleDownload}
            className="flex items-center justify-center w-12 py-3 rounded-ios-lg glass-border"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
              color: 'var(--tg-theme-text-color, #000)',
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="7,10 12,15 17,10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
          </motion.button>
        </motion.div>

        {/* Description */}
        {info.data?.description && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.35 }}
            className="px-4 mt-5"
          >
            <p className="text-[13px] font-semibold uppercase tracking-wider mb-2"
              style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}>
              Описание
            </p>
            <p className="text-[14px] leading-relaxed line-clamp-5"
              style={{ color: 'var(--tg-theme-text-color, #000)' }}>
              {info.data.description}
            </p>
          </motion.div>
        )}

        {/* Chapters / Files */}
        {audioFiles.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.4 }}
            className="mt-5"
          >
            <p className="px-4 text-[13px] font-semibold uppercase tracking-wider mb-2"
              style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}>
              Главы ({audioFiles.length})
            </p>
            <motion.div variants={staggerContainer} initial="hidden" animate="show">
              {audioFiles.map((file, i) => {
                const isCurrent = currentTrack?.topicId === topicId && currentTrack?.fileIndex === file.index
                return (
                  <motion.div key={file.index} variants={staggerItem}>
                    <motion.button
                      whileTap={{ scale: 0.97 }}
                      onClick={() => handlePlayChapter(file, i)}
                      className="w-full flex items-center gap-3 px-4 py-3 text-left"
                      style={{
                        backgroundColor: isCurrent
                          ? 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 8%, transparent)'
                          : 'transparent',
                      }}
                    >
                      <div className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-[12px] font-bold"
                        style={{
                          backgroundColor: isCurrent
                            ? 'var(--tg-theme-button-color, #2481cc)'
                            : 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
                          color: isCurrent
                            ? 'var(--tg-theme-button-text-color, #fff)'
                            : 'var(--tg-theme-hint-color, #999)',
                        }}>
                        {isCurrent && isPlaying ? '▶' : i + 1}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[14px] font-medium truncate"
                          style={{
                            color: isCurrent
                              ? 'var(--tg-theme-button-color, #2481cc)'
                              : 'var(--tg-theme-text-color, #000)',
                          }}>
                          {file.filename.replace(/\.[^/.]+$/, '')}
                        </p>
                        <p className="text-[11px] mt-0.5"
                          style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                          {formatFileSize(file.size_bytes)}
                        </p>
                      </div>
                    </motion.button>
                    <div className="separator mx-4" />
                  </motion.div>
                )
              })}
            </motion.div>
          </motion.div>
        )}

        {/* Empty state for no files */}
        {!files.isLoading && audioFiles.length === 0 && (
          <div className="px-4 mt-8 text-center">
            <p className="text-[15px] font-medium" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
              Файлы ещё не загружены
            </p>
            <p className="text-[13px] mt-1" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
              Нажмите кнопку загрузки, чтобы начать скачивание
            </p>
          </div>
        )}
      </div>
    </motion.div>
  )
}
