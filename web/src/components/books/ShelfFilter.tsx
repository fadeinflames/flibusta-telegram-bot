import { motion } from 'framer-motion'
import { useHaptic } from '../../hooks/useTelegram'
import type { ShelfKey, ShelfCounts } from '../../api/types'
import { SHELF_LABELS, SHELF_ICONS } from '../../api/types'

interface ShelfFilterProps {
  active: ShelfKey
  counts?: ShelfCounts
  onChange: (shelf: ShelfKey) => void
}

const SHELVES: ShelfKey[] = ['all', 'want', 'reading', 'done', 'recommend']

export default function ShelfFilter({ active, counts, onChange }: ShelfFilterProps) {
  const { selection } = useHaptic()

  return (
    <div className="flex gap-2 px-4 py-3 overflow-x-auto no-scrollbar">
      {SHELVES.map((shelf) => {
        const isActive = active === shelf
        const count = counts?.[shelf] ?? 0

        return (
          <button
            key={shelf}
            onClick={() => {
              if (!isActive) {
                selection()
                onChange(shelf)
              }
            }}
            className="flex-shrink-0 flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[13px] font-semibold transition-colors duration-200 relative"
            style={{
              color: isActive
                ? 'var(--tg-theme-button-text-color, #fff)'
                : 'var(--tg-theme-text-color, #000)',
            }}
          >
            {isActive && (
              <motion.div
                layoutId="shelf-pill"
                className="absolute inset-0 rounded-full"
                style={{ backgroundColor: 'var(--tg-theme-button-color, #2481cc)' }}
                transition={{ type: 'spring', damping: 22, stiffness: 280 }}
              />
            )}
            {!isActive && (
              <div
                className="absolute inset-0 rounded-full"
                style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
              />
            )}
            <span className="relative z-10">{SHELF_ICONS[shelf]}</span>
            <span className="relative z-10">{SHELF_LABELS[shelf]}</span>
            {count > 0 && (
              <span className="relative z-10 text-[11px] opacity-70">{count}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
