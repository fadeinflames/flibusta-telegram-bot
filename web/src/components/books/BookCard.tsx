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

const SHELF_BADGES: Record<string, { label: string; color: string }> = {
  want: { label: 'Хочу прочитать', color: '#FF6B6B' },
  reading: { label: 'Читаю', color: '#51CF66' },
  done: { label: 'Прочитано', color: '#339AF0' },
  recommend: { label: 'Рекомендую', color: '#FF922B' },
}

export default function BookCard({ id, title, author, cover, shelf, subtitle }: BookCardProps) {
  const navigate = useNavigate()
  const { impact } = useHaptic()

  const badge = shelf ? SHELF_BADGES[shelf] : null

  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      transition={{ type: 'spring', damping: 15, stiffness: 300 }}
      onClick={() => {
        impact('light')
        navigate(`/book/${id}`)
      }}
      className="flex gap-3.5 p-3.5 w-full text-left rounded-ios-lg transition-colors duration-150"
      style={{ WebkitTapHighlightColor: 'transparent' }}
    >
      {/* Cover */}
      <div
        className="w-[54px] h-[78px] flex-shrink-0 rounded-[10px] overflow-hidden ring-1 ring-black/5"
        style={{
          backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
        }}
      >
        {cover ? (
          <img src={cover} alt={title} className="w-full h-full object-cover" loading="lazy" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-xl opacity-25">
            📖
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0 flex flex-col justify-center py-0.5">
        <h3
          className="text-[15px] font-semibold leading-snug truncate"
          style={{ color: 'var(--tg-theme-text-color, #000)' }}
        >
          {title}
        </h3>
        <p
          className="text-[13px] mt-0.5 truncate"
          style={{ color: 'var(--tg-theme-subtitle-text-color, #6d6d72)' }}
        >
          {author}
        </p>
        {subtitle && (
          <p className="text-[12px] mt-0.5 truncate" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
            {subtitle}
          </p>
        )}
        {badge && (
          <span
            className="inline-flex items-center mt-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold self-start"
            style={{ backgroundColor: `${badge.color}15`, color: badge.color }}
          >
            {badge.label}
          </span>
        )}
      </div>

      {/* Chevron */}
      <div className="flex-shrink-0 flex items-center opacity-30">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 3l5 5-5 5" />
        </svg>
      </div>
    </motion.button>
  )
}
