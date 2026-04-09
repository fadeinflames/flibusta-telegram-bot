import { motion } from 'framer-motion'

interface EmptyStateProps {
  icon: string
  title: string
  subtitle?: string
  action?: React.ReactNode
}

export default function EmptyState({ icon, title, subtitle, action }: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', damping: 24, stiffness: 200, delay: 0.05 }}
      className="flex flex-col items-center justify-center py-20 px-8"
    >
      {/* Decorative background circle + icon */}
      <div className="relative mb-6">
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', damping: 18, stiffness: 180, delay: 0.1 }}
          className="w-[96px] h-[96px] rounded-full flex items-center justify-center"
          style={{
            background: `radial-gradient(
              circle at 40% 35%,
              color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 10%, transparent),
              color-mix(in srgb, var(--tg-theme-secondary-bg-color, #f0f0f0) 80%, transparent)
            )`,
          }}
        >
          <motion.span
            animate={{ y: [0, -4, 0] }}
            transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
            className="text-[44px] select-none"
            style={{ lineHeight: 1 }}
          >
            {icon}
          </motion.span>
        </motion.div>
      </div>

      {/* Title */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.15, duration: 0.3 }}
        className="text-[17px] font-bold text-center"
        style={{
          color: 'var(--tg-theme-text-color, #000)',
          letterSpacing: '-0.01em',
        }}
      >
        {title}
      </motion.p>

      {/* Subtitle */}
      {subtitle && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2, duration: 0.3 }}
          className="text-[14px] text-center mt-2 max-w-[280px] leading-relaxed"
          style={{ color: 'var(--tg-theme-hint-color, #999)' }}
        >
          {subtitle}
        </motion.p>
      )}

      {/* Action slot */}
      {action && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.3 }}
          className="mt-6"
        >
          {action}
        </motion.div>
      )}
    </motion.div>
  )
}
