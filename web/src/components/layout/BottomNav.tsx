import { useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useHaptic } from '../../hooks/useTelegram'

const tabs = [
  { path: '/library', label: 'Книги', icon: BookIcon },
  { path: '/search', label: 'Поиск', icon: SearchIcon },
  { path: '/audiobooks', label: 'Аудио', icon: HeadphonesIcon },
  { path: '/downloads', label: 'Загрузки', icon: DownloadIcon },
  { path: '/profile', label: 'Профиль', icon: PersonIcon },
]

export default function BottomNav() {
  const location = useLocation()
  const navigate = useNavigate()
  const { selection } = useHaptic()

  return (
    <div
      className="flex-shrink-0"
      style={{ paddingBottom: 'var(--safe-area-bottom)' }}
    >
      <nav
        className="mx-3 mb-2 rounded-ios-xl glass glass-border card-elevated-lg"
      >
        <div className="flex justify-around items-center h-[58px] relative">
          {tabs.map((tab) => {
            const isActive = location.pathname === tab.path
            return (
              <button
                key={tab.path}
                onClick={() => {
                  if (!isActive) {
                    selection()
                    navigate(tab.path)
                  }
                }}
                className="flex flex-col items-center justify-center gap-[2px] w-full h-full relative z-10"
              >
                {isActive && (
                  <motion.div
                    layoutId="tab-indicator"
                    className="absolute inset-1 rounded-[14px]"
                    style={{
                      backgroundColor: 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 12%, transparent)',
                    }}
                    transition={{ type: 'spring', damping: 25, stiffness: 280 }}
                  />
                )}
                <div className="relative z-10">
                  <tab.icon active={isActive} />
                </div>
                <span
                  className="relative z-10 text-[10px] font-semibold transition-colors duration-200"
                  style={{
                    color: isActive
                      ? 'var(--tg-theme-button-color, #2481cc)'
                      : 'var(--tg-theme-hint-color, #999)',
                  }}
                >
                  {tab.label}
                </span>
              </button>
            )
          })}
        </div>
      </nav>
    </div>
  )
}

function BookIcon({ active }: { active: boolean }) {
  const color = active ? 'var(--tg-theme-button-color, #2481cc)' : 'var(--tg-theme-hint-color, #999)'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill={active ? color : 'none'} stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: active ? 1 : 0.85 }}>
      <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
    </svg>
  )
}

function SearchIcon({ active }: { active: boolean }) {
  const color = active ? 'var(--tg-theme-button-color, #2481cc)' : 'var(--tg-theme-hint-color, #999)'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={active ? '2.2' : '1.8'} strokeLinecap="round" strokeLinejoin="round" style={{ opacity: active ? 1 : 0.85 }}>
      <circle cx="11" cy="11" r="8" />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  )
}

function HeadphonesIcon({ active }: { active: boolean }) {
  const color = active ? 'var(--tg-theme-button-color, #2481cc)' : 'var(--tg-theme-hint-color, #999)'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={active ? '2.2' : '1.8'} strokeLinecap="round" strokeLinejoin="round" style={{ opacity: active ? 1 : 0.85 }}>
      <path d="M3 18v-6a9 9 0 0118 0v6" />
      <path d="M21 19a2 2 0 01-2 2h-1a2 2 0 01-2-2v-3a2 2 0 012-2h3zM3 19a2 2 0 002 2h1a2 2 0 002-2v-3a2 2 0 00-2-2H3z" />
    </svg>
  )
}

function DownloadIcon({ active }: { active: boolean }) {
  const color = active ? 'var(--tg-theme-button-color, #2481cc)' : 'var(--tg-theme-hint-color, #999)'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={active ? '2.2' : '1.8'} strokeLinecap="round" strokeLinejoin="round" style={{ opacity: active ? 1 : 0.85 }}>
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
      <polyline points="7,10 12,15 17,10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

function PersonIcon({ active }: { active: boolean }) {
  const color = active ? 'var(--tg-theme-button-color, #2481cc)' : 'var(--tg-theme-hint-color, #999)'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill={active ? color : 'none'} stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: active ? 1 : 0.85 }}>
      <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  )
}
