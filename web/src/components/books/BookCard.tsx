import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useHaptic } from '../../hooks/useTelegram'

interface BookCardProps {
  id: string
  title: string
  author: string
  cover?: string
  shelf?: string | null
  subtitle?: string
}

const SHELF_BADGES: Record<string, { label: string; color: string; bg: string }> = {
  want: { label: 'Хочу прочитать', color: '#FF6B6B', bg: 'rgba(255,107,107,0.10)' },
  reading: { label: 'Читаю', color: '#40C057', bg: 'rgba(64,192,87,0.10)' },
  done: { label: 'Прочитано', color: '#339AF0', bg: 'rgba(51,154,240,0.10)' },
  recommend: { label: 'Рекомендую', color: '#FF922B', bg: 'rgba(255,146,43,0.10)' },
}

export default function BookCard({ id, title, author, cover, shelf, subtitle }: BookCardProps) {
  const navigate = useNavigate()
  const { impact } = useHaptic()

  const badge = shelf ? SHELF_BADGES[shelf] : null

  return (
    <motion.button
      whileTap={{ scale: 0.98 }}
      transition={{ type: 'spring', damping: 20, stiffness: 400 }}
      onClick={() => {
        impact('light')
        navigate(`/book/${id}`)
      }}
      className="flex gap-3.5 p-3 w-full text-left rounded-2xl active:bg-[var(--tg-theme-secondary-bg-color)]"
      style={{
        WebkitTapHighlightColor: 'transparent',
        transition: 'background-color 0.15s ease',
      }}
    >
      {/* Cover */}
      <div
        className="w-[56px] h-[80px] flex-shrink-0 rounded-xl overflow-hidden"
        style={{
          backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
          boxShadow:
            '0 2px 8px rgba(0,0,0,0.06), 0 6px 20px rgba(0,0,0,0.04)',
        }}
      >
        {cover ? (
          <img
            src={cover}
            alt={title}
            className="w-full h-full object-cover"
            loading="lazy"
            draggable={false}
          />
        ) : (
          <div
            className="w-full h-full flex items-center justify-center"
            style={{
              background: `linear-gradient(145deg,
                color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 8%, var(--tg-theme-secondary-bg-color, #f0f0f0)),
                var(--tg-theme-secondary-bg-color, #f0f0f0))`,
            }}
          >
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--tg-theme-hint-color, #999)"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ opacity: 0.4 }}
            >
              <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
            </svg>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0 flex flex-col justify-center py-0.5">
        <h3
          className="text-[15px] font-bold leading-[1.3] line-clamp-2"
          style={{
            color: 'var(--tg-theme-text-color, #000)',
            letterSpacing: '-0.01em',
          }}
        >
          {title}
        </h3>
        <p
          className="text-[13px] mt-0.5 truncate"
          style={{
            color: 'var(--tg-theme-subtitle-text-color, #6d6d72)',
            letterSpacing: '0.01em',
          }}
        >
          {author}
        </p>
        {subtitle && (
          <p
            className="text-[12px] mt-0.5 truncate"
            style={{ color: 'var(--tg-theme-hint-color, #999)' }}
          >
            {subtitle}
          </p>
        )}
        {badge && (
          <span
            className="inline-flex items-center mt-1.5 px-2.5 py-[3px] rounded-full text-[11px] font-semibold self-start"
            style={{
              backgroundColor: badge.bg,
              color: badge.color,
              letterSpacing: '0.02em',
            }}
          >
            {badge.label}
          </span>
        )}
      </div>

      {/* Chevron */}
      <div
        className="flex-shrink-0 flex items-center"
        style={{ color: 'var(--tg-theme-hint-color, #999)', opacity: 0.4 }}
      >
        <svg
          width="7"
          height="12"
          viewBox="0 0 7 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M1 1l5 5-5 5" />
        </svg>
      </div>
    </motion.button>
  )
}
