import { motion, AnimatePresence } from 'framer-motion'
import { useAudioPlayer } from '../../contexts/AudioPlayerContext'

interface MiniPlayerProps {
  onExpand: () => void
}

export default function MiniPlayer({ onExpand }: MiniPlayerProps) {
  const { currentTrack, isPlaying, toggle, currentTime, duration } = useAudioPlayer()

  const progress = duration > 0 ? currentTime / duration : 0

  return (
    <AnimatePresence>
      {currentTrack && (
        <motion.div
          initial={{ y: 64, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 64, opacity: 0 }}
          transition={{ type: 'spring', damping: 26, stiffness: 300 }}
          className="flex-shrink-0 relative"
        >
          {/* Gradient progress bar at top */}
          <div
            className="absolute top-0 left-0 right-0 h-[2.5px] overflow-hidden"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)',
            }}
          >
            <motion.div
              className="h-full"
              style={{
                width: `${progress * 100}%`,
                background: 'linear-gradient(90deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 60%, #a855f7))',
              }}
              transition={{ duration: 0.3, ease: 'linear' }}
            />
          </div>

          <button
            onClick={onExpand}
            className="w-full flex items-center gap-3 px-3.5 py-2.5"
            style={{
              backdropFilter: 'blur(32px) saturate(180%)',
              WebkitBackdropFilter: 'blur(32px) saturate(180%)',
              background: 'color-mix(in srgb, var(--tg-theme-bg-color, #fff) 82%, transparent)',
              borderTop: '0.5px solid color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)',
            }}
          >
            {/* Album art icon */}
            <motion.div
              animate={{ rotate: isPlaying ? 360 : 0 }}
              transition={{
                duration: 8,
                repeat: isPlaying ? Infinity : 0,
                ease: 'linear',
              }}
              className="w-11 h-11 rounded-[10px] flex-shrink-0 flex items-center justify-center shadow-sm"
              style={{
                background: 'linear-gradient(135deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 55%, #a855f7))',
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path
                  d="M9 18V5l12-2v13"
                  stroke="white"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity="0.9"
                />
                <circle cx="6" cy="18" r="3" stroke="white" strokeWidth="1.8" opacity="0.9" />
                <circle cx="18" cy="16" r="3" stroke="white" strokeWidth="1.8" opacity="0.9" />
              </svg>
            </motion.div>

            {/* Track info */}
            <div className="flex-1 min-w-0 text-left">
              <p
                className="text-[13px] font-semibold truncate leading-tight"
                style={{ color: 'var(--tg-theme-text-color, #000)' }}
              >
                {currentTrack.chapterName || currentTrack.title}
              </p>
              <p
                className="text-[11px] truncate mt-0.5"
                style={{ color: 'var(--tg-theme-hint-color, #999)' }}
              >
                {currentTrack.author}
              </p>
            </div>

            {/* Play/Pause button */}
            <motion.div
              whileTap={{ scale: 0.82 }}
              onClick={(e) => {
                e.stopPropagation()
                toggle()
              }}
              className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
              style={{
                background: 'linear-gradient(135deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 70%, #a855f7))',
                boxShadow: '0 2px 8px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 30%, transparent)',
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
                    width="14"
                    height="14"
                    viewBox="0 0 14 14"
                    fill="white"
                  >
                    <rect x="1.5" y="0.5" width="3.5" height="13" rx="1.2" />
                    <rect x="9" y="0.5" width="3.5" height="13" rx="1.2" />
                  </motion.svg>
                ) : (
                  <motion.svg
                    key="play"
                    initial={{ scale: 0.5, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    exit={{ scale: 0.5, opacity: 0 }}
                    transition={{ duration: 0.15 }}
                    width="14"
                    height="14"
                    viewBox="0 0 14 14"
                    fill="white"
                  >
                    <path d="M3 1.2L12.5 7L3 12.8V1.2Z" />
                  </motion.svg>
                )}
              </AnimatePresence>
            </motion.div>
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
