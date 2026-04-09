import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAudioPlayer } from '../../contexts/AudioPlayerContext'
import { playerVariants, playerTransition, overlayVariants } from '../../lib/animations'

interface AudioPlayerProps {
  open: boolean
  onClose: () => void
}

function formatTime(seconds: number): string {
  if (!seconds || !isFinite(seconds)) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

const RATES = [0.75, 1, 1.25, 1.5, 2]

export default function AudioPlayer({ open, onClose }: AudioPlayerProps) {
  const {
    currentTrack, isPlaying, currentTime, duration, playbackRate, chapters,
    toggle, seekTo, setRate, nextChapter, prevChapter, stop,
  } = useAudioPlayer()

  const [showChapters, setShowChapters] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [dragTime, setDragTime] = useState(0)

  const progress = duration > 0 ? (isDragging ? dragTime : currentTime) / duration : 0

  const handleSeekBarInteraction = useCallback((e: React.MouseEvent<HTMLDivElement> | React.TouchEvent<HTMLDivElement>) => {
    const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect()
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    return ratio * duration
  }, [duration])

  if (!currentTrack) return null

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            variants={overlayVariants}
            initial="hidden"
            animate="visible"
            exit="hidden"
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50"
            style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
            onClick={onClose}
          />
          <motion.div
            variants={playerVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            transition={playerTransition}
            className="fixed inset-0 z-50 flex flex-col"
            style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 pt-safe-top h-14 flex-shrink-0">
              <motion.button whileTap={{ scale: 0.9 }} onClick={onClose}
                className="w-8 h-8 flex items-center justify-center rounded-full"
                style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}>
                <svg width="14" height="14" viewBox="0 0 14 14" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                  <path d="M1 7h12M7 1l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" transform="rotate(90 7 7)" />
                </svg>
              </motion.button>
              <p className="text-[12px] font-medium uppercase tracking-wider"
                style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                Сейчас играет
              </p>
              <motion.button whileTap={{ scale: 0.9 }} onClick={() => setShowChapters(!showChapters)}
                className="w-8 h-8 flex items-center justify-center rounded-full"
                style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}>
                <svg width="16" height="16" viewBox="0 0 16 16" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                  <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </motion.button>
            </div>

            {showChapters ? (
              /* Chapter list */
              <div className="flex-1 overflow-y-auto px-4 pb-8">
                <p className="text-[13px] font-semibold uppercase tracking-wider mb-3 mt-4"
                  style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}>
                  Главы ({chapters.length})
                </p>
                {chapters.map((ch) => {
                  const isCurrent = ch.index === currentTrack.fileIndex
                  return (
                    <motion.button
                      key={ch.index}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => {
                        const { play } = useAudioPlayer as any // handled by parent
                        // We'll use the play from context indirectly
                        seekTo(0)
                        // Actually navigate via changing track
                      }}
                      className="w-full flex items-center gap-3 px-3 py-3 rounded-ios text-left"
                      style={{
                        backgroundColor: isCurrent
                          ? 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 12%, transparent)'
                          : 'transparent',
                      }}
                    >
                      {isCurrent && (
                        <div className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{ backgroundColor: 'var(--tg-theme-button-color, #2481cc)' }} />
                      )}
                      <span className="text-[14px] truncate"
                        style={{ color: isCurrent ? 'var(--tg-theme-button-color, #2481cc)' : 'var(--tg-theme-text-color, #000)' }}>
                        {ch.name}
                      </span>
                    </motion.button>
                  )
                })}
              </div>
            ) : (
              /* Main player view */
              <div className="flex-1 flex flex-col items-center justify-center px-8">
                {/* Album art */}
                <motion.div
                  animate={{ scale: isPlaying ? 1 : 0.92 }}
                  transition={{ type: 'spring', damping: 20, stiffness: 200 }}
                  className="w-[260px] h-[260px] rounded-[24px] flex items-center justify-center shadow-float-lg mb-8"
                  style={{
                    background: 'linear-gradient(135deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 60%, #a855f7))',
                  }}
                >
                  <span className="text-[80px]">🎧</span>
                </motion.div>

                {/* Track info */}
                <p className="text-[20px] font-bold text-center leading-tight mb-1"
                  style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                  {currentTrack.chapterName || currentTrack.title}
                </p>
                <p className="text-[14px] mb-8"
                  style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                  {currentTrack.author}
                </p>

                {/* Seek bar */}
                <div className="w-full mb-2">
                  <div
                    className="relative h-[6px] rounded-full cursor-pointer"
                    style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 10%, transparent)' }}
                    onMouseDown={(e) => {
                      setIsDragging(true)
                      setDragTime(handleSeekBarInteraction(e))
                    }}
                    onMouseMove={(e) => {
                      if (isDragging) setDragTime(handleSeekBarInteraction(e))
                    }}
                    onMouseUp={(e) => {
                      if (isDragging) {
                        seekTo(handleSeekBarInteraction(e))
                        setIsDragging(false)
                      }
                    }}
                    onMouseLeave={() => {
                      if (isDragging) {
                        seekTo(dragTime)
                        setIsDragging(false)
                      }
                    }}
                    onTouchStart={(e) => {
                      setIsDragging(true)
                      setDragTime(handleSeekBarInteraction(e))
                    }}
                    onTouchMove={(e) => {
                      if (isDragging) setDragTime(handleSeekBarInteraction(e))
                    }}
                    onTouchEnd={() => {
                      if (isDragging) {
                        seekTo(dragTime)
                        setIsDragging(false)
                      }
                    }}
                  >
                    <div
                      className="absolute inset-y-0 left-0 rounded-full"
                      style={{
                        width: `${progress * 100}%`,
                        backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
                      }}
                    />
                    <div
                      className="absolute top-1/2 -translate-y-1/2 w-[14px] h-[14px] rounded-full shadow-sm"
                      style={{
                        left: `calc(${progress * 100}% - 7px)`,
                        backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
                      }}
                    />
                  </div>
                  <div className="flex justify-between mt-1.5">
                    <span className="text-[11px]" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                      {formatTime(isDragging ? dragTime : currentTime)}
                    </span>
                    <span className="text-[11px]" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                      {formatTime(duration)}
                    </span>
                  </div>
                </div>

                {/* Controls */}
                <div className="flex items-center justify-center gap-8 mt-4">
                  <motion.button whileTap={{ scale: 0.85 }} onClick={prevChapter}
                    className="w-12 h-12 flex items-center justify-center">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
                      style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                      <path d="M19 20L9 12l10-8v16zM5 19V5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </motion.button>

                  <motion.button
                    whileTap={{ scale: 0.9 }}
                    onClick={toggle}
                    className="w-[64px] h-[64px] rounded-full flex items-center justify-center shadow-float"
                    style={{ backgroundColor: 'var(--tg-theme-button-color, #2481cc)' }}
                  >
                    {isPlaying ? (
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
                        <rect x="5" y="3" width="5" height="18" rx="1" />
                        <rect x="14" y="3" width="5" height="18" rx="1" />
                      </svg>
                    ) : (
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
                        <path d="M6 3L20 12L6 21V3Z" />
                      </svg>
                    )}
                  </motion.button>

                  <motion.button whileTap={{ scale: 0.85 }} onClick={nextChapter}
                    className="w-12 h-12 flex items-center justify-center">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
                      style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                      <path d="M5 4l10 8-10 8V4zM19 5v14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </motion.button>
                </div>

                {/* Playback rate */}
                <div className="flex gap-2 mt-6">
                  {RATES.map((rate) => (
                    <motion.button
                      key={rate}
                      whileTap={{ scale: 0.9 }}
                      onClick={() => setRate(rate)}
                      className="px-3 py-1.5 rounded-full text-[12px] font-semibold transition-all"
                      style={{
                        backgroundColor: playbackRate === rate
                          ? 'var(--tg-theme-button-color, #2481cc)'
                          : 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
                        color: playbackRate === rate
                          ? 'var(--tg-theme-button-text-color, #fff)'
                          : 'var(--tg-theme-text-color, #000)',
                      }}
                    >
                      {rate}x
                    </motion.button>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
