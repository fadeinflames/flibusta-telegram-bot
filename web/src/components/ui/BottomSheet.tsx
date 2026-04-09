import { motion, AnimatePresence } from 'framer-motion'
import { sheetVariants, sheetTransition, overlayVariants } from '../../lib/animations'

interface BottomSheetProps {
  open: boolean
  onClose: () => void
  children: React.ReactNode
  title?: string
}

export default function BottomSheet({ open, onClose, children, title }: BottomSheetProps) {
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
            className="fixed inset-0 z-40"
            style={{ backgroundColor: 'rgba(0,0,0,0.4)' }}
            onClick={onClose}
          />
          <motion.div
            variants={sheetVariants}
            initial="hidden"
            animate="visible"
            exit="hidden"
            transition={sheetTransition}
            drag="y"
            dragConstraints={{ top: 0 }}
            dragElastic={0.1}
            onDragEnd={(_, info) => {
              if (info.offset.y > 100 || info.velocity.y > 300) onClose()
            }}
            className="fixed bottom-0 left-0 right-0 z-50 rounded-t-[20px] glass glass-border"
            style={{
              paddingBottom: 'calc(var(--safe-area-bottom) + 24px)',
            }}
          >
            {/* Handle */}
            <div className="flex justify-center pt-2.5 pb-1">
              <div
                className="w-9 h-[5px] rounded-full"
                style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 15%, transparent)' }}
              />
            </div>

            {title && (
              <p
                className="text-[17px] font-semibold px-5 pt-2 pb-3"
                style={{ color: 'var(--tg-theme-text-color, #000)' }}
              >
                {title}
              </p>
            )}

            <div className="px-4 pb-4">
              {children}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
