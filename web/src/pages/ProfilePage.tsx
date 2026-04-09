import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../store/auth'
import { useHaptic } from '../hooks/useTelegram'
import type { UserProfile } from '../api/types'

const FORMAT_OPTIONS = ['fb2', 'epub', 'mobi', 'pdf', 'djvu']

export default function ProfilePage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { selection, notification } = useHaptic()
  const tgUser = {
    first_name: user?.first_name || '',
    username: user?.username || '',
    photo_url: user?.photo_url || '',
  }

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

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const p = profile.data

  return (
    <div className="h-full flex flex-col">
      <div className="page-scroll">
        {/* Avatar & name */}
        <div className="flex flex-col items-center pt-8 pb-6 px-4">
          <motion.div
            initial={{ scale: 0.85, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            className="w-[88px] h-[88px] rounded-full overflow-hidden mb-4"
            style={{
              backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
              boxShadow: '0 0 0 3px var(--tg-theme-bg-color, #fff), 0 0 0 5px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 25%, transparent)',
            }}
          >
            {tgUser.photo_url ? (
              <img src={tgUser.photo_url} alt="" className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-3xl text-white font-bold">
                {(tgUser.first_name || '?')[0]}
              </div>
            )}
          </motion.div>
          <h1 className="text-[22px] font-bold" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
            {tgUser.first_name}
          </h1>
          {tgUser.username && (
            <p className="text-[14px] mt-0.5" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
              @{tgUser.username}
            </p>
          )}
        </div>

        {/* Level */}
        {p && (
          <div className="mx-4 mb-4 p-4 rounded-2xl"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
              boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-[16px] font-bold" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                {p.level_name}
              </span>
              <span className="text-[13px] font-semibold" style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}>
                {Math.round(p.level_progress * 100)}%
              </span>
            </div>
            <div className="h-[5px] rounded-full overflow-hidden"
              style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 8%, transparent)' }}>
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${p.level_progress * 100}%` }}
                transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: 0.2 }}
                className="h-full rounded-full"
                style={{ background: `linear-gradient(90deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 70%, #a855f7))` }}
              />
            </div>
          </div>
        )}

        {/* Stats */}
        {p && (
          <div className="grid grid-cols-3 gap-2.5 px-4 mb-6">
            {[
              { value: p.search_count, label: 'Поисков', icon: '🔍' },
              { value: p.download_count, label: 'Загрузок', icon: '📥' },
              { value: p.favorites_count, label: 'В библиотеке', icon: '📚' },
            ].map((stat, i) => (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + i * 0.06, duration: 0.25 }}
                className="flex flex-col items-center p-3.5 rounded-2xl"
                style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
              >
                <span className="text-[20px] mb-0.5">{stat.icon}</span>
                <span className="text-[20px] font-bold" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                  {stat.value}
                </span>
                <span className="text-[11px] mt-0.5 font-medium" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                  {stat.label}
                </span>
              </motion.div>
            ))}
          </div>
        )}

        {/* Default format */}
        <div className="px-4 mb-6">
          <p className="text-[13px] font-semibold uppercase tracking-wider mb-3"
            style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}>
            Формат по умолчанию
          </p>
          <div className="p-4 rounded-2xl"
            style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}>
            <div className="flex gap-2">
              {FORMAT_OPTIONS.map(fmt => {
                const isActive = prefs.data?.default_format === fmt
                return (
                  <button
                    key={fmt}
                    onClick={() => { selection(); updateFormat.mutate(fmt) }}
                    className="px-3 py-2 rounded-xl text-[13px] font-bold transition-all duration-200"
                    style={{
                      color: isActive ? 'var(--tg-theme-button-text-color, #fff)' : 'var(--tg-theme-text-color, #000)',
                      backgroundColor: isActive
                        ? 'var(--tg-theme-button-color, #2481cc)'
                        : 'var(--tg-theme-bg-color, #fff)',
                      boxShadow: isActive ? '0 2px 8px rgba(0,0,0,0.12)' : 'none',
                    }}
                  >
                    {fmt.toUpperCase()}
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {/* Logout */}
        <div className="px-4 mb-4">
          <button
            onClick={handleLogout}
            className="w-full py-3.5 rounded-2xl text-[15px] font-semibold transition-transform active:scale-[0.98]"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
              color: 'var(--tg-theme-destructive-text-color, #ff3b30)',
            }}
          >
            Выйти
          </button>
        </div>

        {p?.first_seen && (
          <p className="text-center text-[12px] mt-2 pb-4" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
            Участник с {new Date(p.first_seen).toLocaleDateString('ru-RU', { year: 'numeric', month: 'long' })}
          </p>
        )}
      </div>
    </div>
  )
}
