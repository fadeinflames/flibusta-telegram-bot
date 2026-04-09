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
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', damping: 20, stiffness: 200, delay: 0.1 }}
      className="flex flex-col items-center justify-center py-20 px-8"
    >
      <motion.div
        animate={{ y: [0, -6, 0] }}
        transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
        className="text-[56px] mb-5"
      >
        {icon}
      </motion.div>
      <p
        className="text-[17px] font-semibold text-center"
        style={{ color: 'var(--tg-theme-text-color, #000)' }}
      >
        {title}
      </p>
      {subtitle && (
        <p
          className="text-[14px] text-center mt-2 max-w-[260px]"
          style={{ color: 'var(--tg-theme-hint-color, #999)' }}
        >
          {subtitle}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </motion.div>
  )
}
