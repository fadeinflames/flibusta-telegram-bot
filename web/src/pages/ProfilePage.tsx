import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '../api/client'
import { useHaptic, getTelegramUser } from '../hooks/useTelegram'
import { pageVariants, pageTransition } from '../lib/animations'
import type { UserProfile } from '../api/types'

const FORMAT_OPTIONS = ['fb2', 'epub', 'mobi', 'pdf', 'djvu']

const STAT_GRADIENTS = [
  'linear-gradient(135deg, #667eea15, #764ba215)',
  'linear-gradient(135deg, #f093fb15, #f5576c15)',
  'linear-gradient(135deg, #4facfe15, #00f2fe15)',
]

export default function ProfilePage() {
  const queryClient = useQueryClient()
  const { selection, notification } = useHaptic()
  const tgUser = getTelegramUser()

  const profile = useQuery<UserProfile>({
    queryKey: ['profile'],
    queryFn: () => api.getProfile() as Promise<UserProfile>,
  })

  const prefs = useQuery<{ default_format: string; books_per_page: number }>({
    queryKey: ['preferences'],
    queryFn: () => api.getPreferences() as Promise<{ default_format: string; books_per_page: number }>,
  })

  const updateFormat = useMutation({
    mutationFn: (format: string) => api.updatePreferences({ default_format: format }),
    onSuccess: () => {
      notification('success')
      queryClient.invalidateQueries({ queryKey: ['preferences'] })
    },
  })

  const p = profile.data

  return (
    <motion.div
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={pageTransition}
      className="h-full flex flex-col"
    >
      <div className="page-scroll">
        {/* Avatar & name */}
        <div className="flex flex-col items-center pt-8 pb-5 px-4">
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', damping: 15, stiffness: 200, delay: 0.1 }}
            className="w-[88px] h-[88px] rounded-full overflow-hidden ring-4 ring-offset-2 mb-4"
            style={{
              backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
              '--tw-ring-color': 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 20%, transparent)',
              '--tw-ring-offset-color': 'var(--tg-theme-bg-color, #fff)',
            } as React.CSSProperties}
          >
            {tgUser?.photo_url ? (
              <img src={tgUser.photo_url} alt="" className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-3xl text-white font-bold">
                {(tgUser?.first_name || '?')[0]}
              </div>
            )}
          </motion.div>
          <h1 className="text-[24px] font-bold" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
            {tgUser?.first_name} {tgUser?.last_name || ''}
          </h1>
          {tgUser?.username && (
            <p className="text-[14px] mt-0.5" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
              @{tgUser.username}
            </p>
          )}
        </div>

        {/* Achievement */}
        {p && (
          <div className="mx-4 mb-4 p-4 rounded-ios-lg glass-border card-elevated"
            style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}>
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-[17px] font-bold" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                {p.level_name}
              </span>
              <span className="text-[13px] font-semibold" style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}>
                {Math.round(p.level_progress * 100)}%
              </span>
            </div>
            <div className="h-[6px] rounded-full overflow-hidden"
              style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 8%, transparent)' }}>
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${p.level_progress * 100}%` }}
                transition={{ duration: 1, ease: [0.22, 1, 0.36, 1], delay: 0.3 }}
                className="h-full rounded-full"
                style={{
                  background: `linear-gradient(90deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 70%, #a855f7))`,
                }}
              />
            </div>
          </div>
        )}

        {/* Stats grid */}
        {p && (
          <div className="grid grid-cols-3 gap-2.5 px-4 mb-5">
            {[
              { value: p.search_count, label: 'Поисков' },
              { value: p.download_count, label: 'Загрузок' },
              { value: p.favorites_count, label: 'В библиотеке' },
            ].map((stat, i) => (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 + i * 0.08, type: 'spring', damping: 20 }}
                className="flex flex-col items-center p-3.5 rounded-ios-lg glass-border"
                style={{ background: STAT_GRADIENTS[i], backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
              >
                <span className="text-[24px] font-bold" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                  {stat.value}
                </span>
                <span className="text-[11px] mt-0.5 font-medium" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                  {stat.label}
                </span>
              </motion.div>
            ))}
          </div>
        )}

        {/* Settings */}
        <div className="px-4 mt-2">
          <p className="text-[13px] font-semibold uppercase tracking-wider mb-2.5"
            style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}>
            Настройки
          </p>
          <div className="rounded-ios-lg overflow-hidden glass-border card-elevated"
            style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}>
            <div className="px-4 py-3.5">
              <p className="text-[15px] font-semibold mb-3" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                Формат по умолчанию
              </p>
              <div className="flex gap-2">
                {FORMAT_OPTIONS.map(fmt => {
                  const isActive = prefs.data?.default_format === fmt
                  return (
                    <motion.button
                      key={fmt}
                      whileTap={{ scale: 0.93 }}
                      onClick={() => { selection(); updateFormat.mutate(fmt) }}
                      className="px-3 py-1.5 rounded-full text-[13px] font-semibold transition-all duration-200 relative"
                      style={{
                        color: isActive ? 'var(--tg-theme-button-text-color, #fff)' : 'var(--tg-theme-text-color, #000)',
                      }}
                    >
                      {isActive && (
                        <motion.div
                          layoutId="format-pill"
                          className="absolute inset-0 rounded-full"
                          style={{ backgroundColor: 'var(--tg-theme-button-color, #2481cc)' }}
                          transition={{ type: 'spring', damping: 22, stiffness: 280 }}
                        />
                      )}
                      {!isActive && (
                        <div className="absolute inset-0 rounded-full" style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }} />
                      )}
                      <span className="relative z-10">{fmt.toUpperCase()}</span>
                    </motion.button>
                  )
                })}
              </div>
            </div>
          </div>
        </div>

        {p?.first_seen && (
          <p className="text-center text-[12px] mt-8 pb-4" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
            Участник с {new Date(p.first_seen).toLocaleDateString('ru-RU', { year: 'numeric', month: 'long' })}
          </p>
        )}
      </div>
    </motion.div>
  )
}
