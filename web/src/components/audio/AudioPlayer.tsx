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
            style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
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
            <div className="flex items-center justify-between px-5 pt-safe-top h-14 flex-shrink-0">
              <motion.button
                whileTap={{ scale: 0.88 }}
                onClick={onClose}
                className="w-9 h-9 flex items-center justify-center rounded-full"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)',
                }}
              >
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <path
                    d="M9 3v12M4 10l5 5 5-5"
                    stroke="var(--tg-theme-text-color, #000)"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </motion.button>

              <p
                className="text-[11px] font-semibold uppercase tracking-[0.08em]"
                style={{ color: 'var(--tg-theme-hint-color, #999)' }}
              >
                {'\u0421\u0435\u0439\u0447\u0430\u0441 \u0438\u0433\u0440\u0430\u0435\u0442'}
              </p>

              <motion.button
                whileTap={{ scale: 0.88 }}
                onClick={() => setShowChapters(!showChapters)}
                className="w-9 h-9 flex items-center justify-center rounded-full"
                style={{
                  backgroundColor: showChapters
                    ? 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 15%, transparent)'
                    : 'color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)',
                }}
              >
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <path
                    d="M3 5h12M3 9h12M3 13h12"
                    stroke={showChapters ? 'var(--tg-theme-button-color, #2481cc)' : 'var(--tg-theme-text-color, #000)'}
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                </svg>
              </motion.button>
            </div>

            <AnimatePresence mode="wait" initial={false}>
              {showChapters ? (
                /* ──────── Chapter list ──────── */
                <motion.div
                  key="chapters"
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  transition={{ duration: 0.2, ease: 'easeOut' }}
                  className="flex-1 overflow-y-auto px-5 pb-8"
                >
                  <p
                    className="text-[12px] font-semibold uppercase tracking-[0.06em] mb-3 mt-4"
                    style={{ color: 'var(--tg-theme-hint-color, #999)' }}
                  >
                    {'\u0413\u043B\u0430\u0432\u044B'} ({chapters.length})
                  </p>
                  <div className="flex flex-col gap-1">
                    {chapters.map((ch) => {
                      const isCurrent = ch.index === currentTrack.fileIndex
                      return (
                        <motion.button
                          key={ch.index}
                          whileTap={{ scale: 0.97 }}
                          onClick={() => {
                            seekTo(0)
                          }}
                          className="w-full flex items-center gap-3 px-4 py-3.5 rounded-[14px] text-left transition-colors"
                          style={{
                            backgroundColor: isCurrent
                              ? 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 10%, transparent)'
                              : 'transparent',
                          }}
                        >
                          {/* Chapter indicator */}
                          <div
                            className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-[11px] font-bold"
                            style={{
                              backgroundColor: isCurrent
                                ? 'var(--tg-theme-button-color, #2481cc)'
                                : 'color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)',
                              color: isCurrent
                                ? 'var(--tg-theme-button-text-color, #fff)'
                                : 'var(--tg-theme-hint-color, #999)',
                            }}
                          >
                            {isCurrent ? (
                              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                                <rect x="2" y="1" width="2.5" height="10" rx="0.8" />
                                <rect x="7.5" y="1" width="2.5" height="10" rx="0.8" />
                              </svg>
                            ) : (
                              ch.index + 1
                            )}
                          </div>

                          <span
                            className="text-[14px] truncate flex-1"
                            style={{
                              color: isCurrent
                                ? 'var(--tg-theme-button-color, #2481cc)'
                                : 'var(--tg-theme-text-color, #000)',
                              fontWeight: isCurrent ? 600 : 400,
                            }}
                          >
                            {ch.name}
                          </span>

                          {isCurrent && (
                            <motion.div
                              layoutId="chapter-indicator"
                              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                              style={{ backgroundColor: 'var(--tg-theme-button-color, #2481cc)' }}
                            />
                          )}
                        </motion.button>
                      )
                    })}
                  </div>
                </motion.div>
              ) : (
                /* ──────── Main player view ──────── */
                <motion.div
                  key="player"
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ duration: 0.2, ease: 'easeOut' }}
                  className="flex-1 flex flex-col items-center justify-center px-8"
                >
                  {/* Album art */}
                  <motion.div
                    animate={{
                      scale: isPlaying ? 1 : 0.88,
                      borderRadius: isPlaying ? '28px' : '24px',
                    }}
                    transition={{ type: 'spring', damping: 18, stiffness: 180 }}
                    className="w-[270px] h-[270px] flex items-center justify-center mb-10 relative overflow-hidden"
                    style={{
                      background: currentTrack.cover
                        ? undefined
                        : 'linear-gradient(145deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 50%, #7c3aed))',
                      boxShadow: isPlaying
                        ? '0 20px 60px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 35%, transparent), 0 8px 20px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 20%, transparent)'
                        : '0 10px 30px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 20%, transparent)',
                    }}
                  >
                    {currentTrack.cover ? (
                      <img
                        src={currentTrack.cover}
                        alt={currentTrack.title}
                        className="absolute inset-0 w-full h-full object-cover"
                      />
                    ) : (
                      <>
                        {/* Decorative rings */}
                        <div
                          className="absolute inset-0"
                          style={{
                            background: 'radial-gradient(circle at 30% 30%, rgba(255,255,255,0.15) 0%, transparent 60%)',
                          }}
                        />
                        <div
                          className="absolute w-[120px] h-[120px] rounded-full border border-white/10"
                          style={{ top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }}
                        />
                        <div
                          className="absolute w-[180px] h-[180px] rounded-full border border-white/5"
                          style={{ top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }}
                        />
                        <svg width="72" height="72" viewBox="0 0 24 24" fill="none" className="relative z-10">
                          <path d="M9 18V5l12-2v13" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.85" />
                          <circle cx="6" cy="18" r="3" stroke="white" strokeWidth="1.5" opacity="0.85" />
                          <circle cx="18" cy="16" r="3" stroke="white" strokeWidth="1.5" opacity="0.85" />
                        </svg>
                      </>
                    )}
                  </motion.div>

                  {/* Track info */}
                  <div className="w-full text-center mb-8">
                    <p
                      className="text-[22px] font-bold leading-tight mb-1.5"
                      style={{ color: 'var(--tg-theme-text-color, #000)' }}
                    >
                      {currentTrack.chapterName || currentTrack.title}
                    </p>
                    <p
                      className="text-[14px] font-medium"
                      style={{ color: 'var(--tg-theme-hint-color, #999)' }}
                    >
                      {currentTrack.author}
                    </p>
                  </div>

                  {/* Seek bar */}
                  <div className="w-full mb-1">
                    <div
                      className="relative h-[5px] rounded-full cursor-pointer group"
                      style={{
                        backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 8%, transparent)',
                      }}
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
                      {/* Filled track */}
                      <div
                        className="absolute inset-y-0 left-0 rounded-full"
                        style={{
                          width: `${progress * 100}%`,
                          background: 'linear-gradient(90deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 65%, #a855f7))',
                        }}
                      />
                      {/* Thumb */}
                      <motion.div
                        animate={{
                          scale: isDragging ? 1.3 : 1,
                        }}
                        transition={{ duration: 0.15 }}
                        className="absolute top-1/2 -translate-y-1/2 w-[15px] h-[15px] rounded-full"
                        style={{
                          left: `calc(${progress * 100}% - 7.5px)`,
                          background: 'var(--tg-theme-button-color, #2481cc)',
                          boxShadow: '0 2px 8px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 40%, transparent)',
                        }}
                      />
                    </div>

                    {/* Time labels */}
                    <div className="flex justify-between mt-2">
                      <span
                        className="text-[11px] font-medium tabular-nums"
                        style={{ color: 'var(--tg-theme-hint-color, #999)' }}
                      >
                        {formatTime(isDragging ? dragTime : currentTime)}
                      </span>
                      <span
                        className="text-[11px] font-medium tabular-nums"
                        style={{ color: 'var(--tg-theme-hint-color, #999)' }}
                      >
                        -{formatTime(Math.max(0, duration - (isDragging ? dragTime : currentTime)))}
                      </span>
                    </div>
                  </div>

                  {/* Transport controls */}
                  <div className="flex items-center justify-center gap-6 mt-4">
                    {/* Previous */}
                    <motion.button
                      whileTap={{ scale: 0.82 }}
                      onClick={prevChapter}
                      className="w-14 h-14 flex items-center justify-center rounded-full"
                      style={{
                        backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 5%, transparent)',
                      }}
                    >
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                        <path
                          d="M19 20L9 12l10-8v16zM5 19V5"
                          stroke="var(--tg-theme-text-color, #000)"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </motion.button>

                    {/* Play/Pause */}
                    <motion.button
                      whileTap={{ scale: 0.88 }}
                      onClick={toggle}
                      className="w-[72px] h-[72px] rounded-full flex items-center justify-center"
                      style={{
                        background: 'linear-gradient(145deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 70%, #7c3aed))',
                        boxShadow: '0 6px 20px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 35%, transparent)',
                      }}
                    >
                      <AnimatePresence mode="wait" initial={false}>
                        {isPlaying ? (
                          <motion.svg
                            key="pause"
                            initial={{ scale: 0.5, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.5, opacity: 0 }}
                            transition={{ duration: 0.15 }}
                            width="26"
                            height="26"
                            viewBox="0 0 24 24"
                            fill="white"
                          >
                            <rect x="5" y="3" width="5" height="18" rx="1.5" />
                            <rect x="14" y="3" width="5" height="18" rx="1.5" />
                          </motion.svg>
                        ) : (
                          <motion.svg
                            key="play"
                            initial={{ scale: 0.5, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.5, opacity: 0 }}
                            transition={{ duration: 0.15 }}
                            width="26"
                            height="26"
                            viewBox="0 0 24 24"
                            fill="white"
                          >
                            <path d="M7 3.5L20 12L7 20.5V3.5Z" />
                          </motion.svg>
                        )}
                      </AnimatePresence>
                    </motion.button>

                    {/* Next */}
                    <motion.button
                      whileTap={{ scale: 0.82 }}
                      onClick={nextChapter}
                      className="w-14 h-14 flex items-center justify-center rounded-full"
                      style={{
                        backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 5%, transparent)',
                      }}
                    >
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                        <path
                          d="M5 4l10 8-10 8V4zM19 5v14"
                          stroke="var(--tg-theme-text-color, #000)"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </motion.button>
                  </div>

                  {/* Playback rate pills */}
                  <div className="flex gap-2 mt-7">
                    {RATES.map((rate) => {
                      const isActive = playbackRate === rate
                      return (
                        <motion.button
                          key={rate}
                          whileTap={{ scale: 0.9 }}
                          onClick={() => setRate(rate)}
                          className="px-3.5 py-1.5 rounded-full text-[12px] font-semibold transition-all duration-200"
                          style={{
                            backgroundColor: isActive
                              ? 'var(--tg-theme-button-color, #2481cc)'
                              : 'color-mix(in srgb, var(--tg-theme-text-color, #000) 5%, transparent)',
                            color: isActive
                              ? 'var(--tg-theme-button-text-color, #fff)'
                              : 'var(--tg-theme-hint-color, #999)',
                            boxShadow: isActive
                              ? '0 2px 8px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 30%, transparent)'
                              : 'none',
                          }}
                        >
                          {rate}x
                        </motion.button>
                      )
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
