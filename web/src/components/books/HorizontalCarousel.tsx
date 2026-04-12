import { useRef, useState, useEffect } from 'react'
import { motion } from 'framer-motion'

interface HorizontalCarouselProps {
  title: string
  subtitle?: string
  icon?: React.ReactNode
  children: React.ReactNode
  onSeeAll?: () => void
}

export default function HorizontalCarousel({
  title,
  subtitle,
  icon,
  children,
  onSeeAll,
}: HorizontalCarouselProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)

  const updateScrollState = () => {
    const el = scrollRef.current
    if (!el) return
    setCanScrollLeft(el.scrollLeft > 4)
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 4)
  }

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    updateScrollState()
    el.addEventListener('scroll', updateScrollState, { passive: true })
    const observer = new ResizeObserver(updateScrollState)
    observer.observe(el)
    return () => {
      el.removeEventListener('scroll', updateScrollState)
      observer.disconnect()
    }
  }, [])

  return (
    <div className="mb-6">
      {/* Header */}
      <div className="flex items-center justify-between px-5 mb-3">
        <div className="flex items-center gap-2.5">
          {icon && <div className="flex-shrink-0">{icon}</div>}
          <div>
            <h2
              className="text-[17px] font-bold tracking-tight"
              style={{ color: 'var(--tg-theme-text-color, #000)' }}
            >
              {title}
            </h2>
            {subtitle && (
              <p className="text-[12px] mt-0.5" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {onSeeAll && (
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={onSeeAll}
            className="text-[13px] font-semibold px-2 py-1"
            style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}
          >
            Все
          </motion.button>
        )}
      </div>

      {/* Scrollable area */}
      <div className="relative">
        <div
          ref={scrollRef}
          className="flex gap-3 px-5 overflow-x-auto no-scrollbar pb-1"
          style={{
            scrollSnapType: 'x proximity',
            WebkitOverflowScrolling: 'touch',
          }}
        >
          {children}
        </div>

        {/* Fade edges */}
        {canScrollLeft && (
          <div
            className="absolute left-0 top-0 bottom-1 w-8 pointer-events-none"
            style={{
              background: 'linear-gradient(to right, var(--tg-theme-bg-color, #fff), transparent)',
            }}
          />
        )}
        {canScrollRight && (
          <div
            className="absolute right-0 top-0 bottom-1 w-8 pointer-events-none"
            style={{
              background: 'linear-gradient(to left, var(--tg-theme-bg-color, #fff), transparent)',
            }}
          />
        )}
      </div>
    </div>
  )
}
