import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useHaptic } from '../../hooks/useTelegram'

interface BookCoverCardProps {
  id: string
  title: string
  author: string
  cover?: string
  shelf?: string | null
  progress?: number // 0-100
  badge?: string // "Новое", "Читаю" etc
  size?: 'sm' | 'md' | 'lg'
}

const COVER_GRADIENTS = [
  'linear-gradient(135deg, #667eea, #764ba2)',
  'linear-gradient(135deg, #f093fb, #f5576c)',
  'linear-gradient(135deg, #4facfe, #00f2fe)',
  'linear-gradient(135deg, #43e97b, #38f9d7)',
  'linear-gradient(135deg, #fa709a, #fee140)',
  'linear-gradient(135deg, #a18cd1, #fbc2eb)',
  'linear-gradient(135deg, #fccb90, #d57eeb)',
  'linear-gradient(135deg, #e0c3fc, #8ec5fc)',
]

function hashId(str: string): number {
  let h = 0
  for (let i = 0; i < str.length; i++) h = ((h << 5) - h + str.charCodeAt(i)) | 0
  return Math.abs(h)
}

const SIZES = {
  sm: { w: 100, h: 140, titleSize: 12, authorSize: 11 },
  md: { w: 120, h: 168, titleSize: 13, authorSize: 12 },
  lg: { w: 140, h: 196, titleSize: 14, authorSize: 12 },
}

export default function BookCoverCard({
  id, title, author, cover, progress, badge, size = 'md',
}: BookCoverCardProps) {
  const navigate = useNavigate()
  const { impact } = useHaptic()
  const s = SIZES[size]
  const placeholderGradient = COVER_GRADIENTS[hashId(id) % COVER_GRADIENTS.length]

  return (
    <motion.button
      whileTap={{ scale: 0.95 }}
      transition={{ type: 'spring', damping: 20, stiffness: 400 }}
      onClick={() => {
        impact('light')
        navigate(`/book/${id}`)
      }}
      className="flex-shrink-0 text-left"
      style={{ width: s.w, WebkitTapHighlightColor: 'transparent' }}
    >
      {/* Cover */}
      <div
        className="relative rounded-xl overflow-hidden"
        style={{
          width: s.w,
          height: s.h,
          boxShadow: '0 4px 16px rgba(0,0,0,0.12), 0 1px 4px rgba(0,0,0,0.08)',
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
            style={{ background: placeholderGradient }}
          >
            <span className="text-[28px] font-bold text-white" style={{ opacity: 0.85, textShadow: '0 1px 4px rgba(0,0,0,0.15)' }}>
              {(title || '?')[0].toUpperCase()}
            </span>
          </div>
        )}

        {/* Shine overlay */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'linear-gradient(135deg, rgba(255,255,255,0.12) 0%, transparent 50%)',
          }}
        />

        {/* Badge */}
        {badge && (
          <div
            className="absolute top-1.5 left-1.5 px-2 py-0.5 rounded-md text-[9px] font-bold uppercase tracking-wide"
            style={{
              backgroundColor: 'rgba(0,0,0,0.55)',
              backdropFilter: 'blur(8px)',
              color: '#fff',
            }}
          >
            {badge}
          </div>
        )}

        {/* Progress bar at bottom */}
        {progress !== undefined && progress > 0 && (
          <div className="absolute bottom-0 left-0 right-0 h-[3px]" style={{ backgroundColor: 'rgba(0,0,0,0.2)' }}>
            <div
              className="h-full"
              style={{
                width: `${Math.min(100, progress)}%`,
                backgroundColor: progress >= 100 ? '#40C057' : '#fff',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
        )}
      </div>

      {/* Title + Author */}
      <p
        className="mt-2 font-semibold leading-tight line-clamp-2"
        style={{
          fontSize: s.titleSize,
          color: 'var(--tg-theme-text-color, #000)',
          letterSpacing: '-0.01em',
        }}
      >
        {title}
      </p>
      <p
        className="mt-0.5 truncate"
        style={{
          fontSize: s.authorSize,
          color: 'var(--tg-theme-subtitle-text-color, #6d6d72)',
        }}
      >
        {author}
      </p>
    </motion.button>
  )
}
