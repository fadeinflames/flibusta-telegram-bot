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
          initial={{ y: 60, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 60, opacity: 0 }}
          transition={{ type: 'spring', damping: 24, stiffness: 260 }}
          className="flex-shrink-0 relative"
        >
          {/* Progress bar */}
          <div className="absolute top-0 left-0 right-0 h-[2px]"
            style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 8%, transparent)' }}>
            <motion.div
              className="h-full"
              style={{
                width: `${progress * 100}%`,
                backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
              }}
              transition={{ duration: 0.3 }}
            />
          </div>

          <button
            onClick={onExpand}
            className="w-full flex items-center gap-3 px-4 py-2.5 glass glass-border"
          >
            {/* Album art placeholder */}
            <div
              className="w-10 h-10 rounded-ios flex-shrink-0 flex items-center justify-center text-lg shadow-sm"
              style={{ backgroundColor: 'var(--tg-theme-button-color, #2481cc)', color: '#fff' }}
            >
              🎧
            </div>

            {/* Track info */}
            <div className="flex-1 min-w-0 text-left">
              <p className="text-[13px] font-semibold truncate"
                style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                {currentTrack.chapterName || currentTrack.title}
              </p>
              <p className="text-[11px] truncate"
                style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                {currentTrack.author}
              </p>
            </div>

            {/* Play/Pause */}
            <motion.div
              whileTap={{ scale: 0.85 }}
              onClick={(e) => { e.stopPropagation(); toggle() }}
              className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: 'var(--tg-theme-button-color, #2481cc)' }}
            >
              {isPlaying ? (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="white">
                  <rect x="1" y="0" width="4" height="14" rx="1" />
                  <rect x="9" y="0" width="4" height="14" rx="1" />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="white">
                  <path d="M2 0.5L13 7L2 13.5V0.5Z" />
                </svg>
              )}
            </motion.div>
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
