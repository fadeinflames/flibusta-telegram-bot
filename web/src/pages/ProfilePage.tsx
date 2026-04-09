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
        {/* Profile header */}
        <div className="flex flex-col items-center pt-8 pb-6 px-5">
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', damping: 20, stiffness: 200 }}
            className="relative mb-4"
          >
            <div
              className="w-[96px] h-[96px] rounded-full overflow-hidden"
              style={{
                backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
                boxShadow: '0 0 0 4px var(--tg-theme-bg-color, #fff), 0 0 0 6px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 20%, transparent), 0 8px 32px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 25%, transparent)',
              }}
            >
              {tgUser.photo_url ? (
                <img src={tgUser.photo_url} alt="" className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-[36px] text-white font-bold">
                  {(tgUser.first_name || '?')[0]}
                </div>
              )}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, duration: 0.3 }}
            className="text-center"
          >
            <h1
              className="text-[24px] font-bold tracking-tight"
              style={{ color: 'var(--tg-theme-text-color, #000)' }}
            >
              {tgUser.first_name}
            </h1>
            {tgUser.username && (
              <p className="text-[15px] mt-0.5 font-medium" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                @{tgUser.username}
              </p>
            )}
          </motion.div>
        </div>

        {/* Level/progress card */}
        {p && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15, duration: 0.3 }}
            className="mx-5 mb-5 p-5 rounded-2xl"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-[14px]"
                  style={{
                    background: 'linear-gradient(135deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 60%, #7c3aed))',
                    color: 'var(--tg-theme-button-text-color, #fff)',
                  }}
                >
                  {p.level_index + 1}
                </div>
                <span className="text-[17px] font-bold" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                  {p.level_name}
                </span>
              </div>
              <span
                className="text-[14px] font-bold"
                style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}
              >
                {Math.round(p.level_progress * 100)}%
              </span>
            </div>
            <div
              className="h-[6px] rounded-full overflow-hidden"
              style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)' }}
            >
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${p.level_progress * 100}%` }}
                transition={{ duration: 1, ease: [0.22, 1, 0.36, 1], delay: 0.3 }}
                className="h-full rounded-full"
                style={{
                  background: 'linear-gradient(90deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 60%, #a855f7))',
                }}
              />
            </div>
          </motion.div>
        )}

        {/* Statistics cards */}
        {p && (
          <div className="grid grid-cols-3 gap-2.5 px-5 mb-6">
            {[
              { value: p.search_count, label: 'Поисков', color: '#667eea', icon: (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#667eea" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
              )},
              { value: p.download_count, label: 'Загрузок', color: '#43e97b', icon: (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#43e97b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                  <polyline points="7,10 12,15 17,10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
              )},
              { value: p.favorites_count, label: 'В библиотеке', color: '#f5576c', icon: (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#f5576c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
                </svg>
              )},
            ].map((stat, i) => (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 + i * 0.06, duration: 0.3 }}
                className="flex flex-col items-center p-4 rounded-2xl relative overflow-hidden"
                style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
              >
                <div className="absolute top-0 left-0 right-0 h-[3px] rounded-t-2xl" style={{ background: `linear-gradient(90deg, ${stat.color}, ${stat.color}88)` }} />
                <div className="mb-2">{stat.icon}</div>
                <span className="text-[22px] font-bold" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
                  {stat.value}
                </span>
                <span className="text-[11px] mt-0.5 font-medium" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
                  {stat.label}
                </span>
              </motion.div>
            ))}
          </div>
        )}

        {/* Format selector */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.3 }}
          className="px-5 mb-6"
        >
          <p
            className="text-[13px] font-semibold uppercase tracking-wider mb-3"
            style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}
          >
            Формат по умолчанию
          </p>
          <div
            className="p-1.5 rounded-2xl flex gap-1"
            style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
          >
            {FORMAT_OPTIONS.map(fmt => {
              const isActive = prefs.data?.default_format === fmt
              return (
                <motion.button
                  key={fmt}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => { selection(); updateFormat.mutate(fmt) }}
                  className="flex-1 py-2.5 rounded-xl text-[13px] font-bold transition-all duration-200 relative"
                  style={{
                    color: isActive ? 'var(--tg-theme-button-text-color, #fff)' : 'var(--tg-theme-text-color, #000)',
                    backgroundColor: isActive ? 'var(--tg-theme-button-color, #2481cc)' : 'transparent',
                    boxShadow: isActive ? '0 2px 8px color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 30%, transparent)' : 'none',
                  }}
                >
                  {fmt.toUpperCase()}
                </motion.button>
              )
            })}
          </div>
        </motion.div>

        {/* Logout */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.3 }}
          className="px-5 mb-4"
        >
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={handleLogout}
            className="w-full py-4 rounded-2xl text-[16px] font-semibold"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--tg-theme-destructive-text-color, #ff3b30) 8%, transparent)',
              color: 'var(--tg-theme-destructive-text-color, #ff3b30)',
            }}
          >
            Выйти
          </motion.button>
        </motion.div>

        {/* Member since */}
        {p?.first_seen && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5, duration: 0.3 }}
            className="text-center text-[13px] mt-2 pb-6 font-medium"
            style={{ color: 'var(--tg-theme-hint-color, #999)' }}
          >
            Участник с {new Date(p.first_seen).toLocaleDateString('ru-RU', { year: 'numeric', month: 'long' })}
          </motion.p>
        )}
      </div>
    </div>
  )
}
