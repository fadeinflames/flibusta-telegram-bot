import { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useLocation } from 'react-router-dom'
import { useTelegram } from './hooks/useTelegram'
import { loginWithInitData, storeAuth, getStoredToken } from './api/client'
import BottomNav from './components/layout/BottomNav'
import MiniPlayer from './components/audio/MiniPlayer'
import AudioPlayer from './components/audio/AudioPlayer'
import LibraryPage from './pages/LibraryPage'
import SearchPage from './pages/SearchPage'
import AudiobooksPage from './pages/AudiobooksPage'
import AudiobookDetailPage from './pages/AudiobookDetailPage'
import DownloadsPage from './pages/DownloadsPage'
import ProfilePage from './pages/ProfilePage'
import BookDetailPage from './pages/BookDetailPage'

type AuthState = 'loading' | 'authenticated' | 'no_telegram'

export default function App() {
  const tg = useTelegram()
  const location = useLocation()
  const [playerOpen, setPlayerOpen] = useState(false)
  const [authState, setAuthState] = useState<AuthState>(() =>
    getStoredToken() ? 'authenticated' : 'loading'
  )
  const [authError, setAuthError] = useState<string | null>(null)

  useEffect(() => {
    // Already have a valid token
    if (getStoredToken()) {
      setAuthState('authenticated')
      return
    }

    const initData = window.Telegram?.WebApp?.initData
    if (!initData) {
      setAuthState('no_telegram')
      return
    }

    // Auto-login with initData
    loginWithInitData(initData)
      .then(({ access_token, user }) => {
        storeAuth(access_token, user)
        setAuthState('authenticated')
      })
      .catch((err) => {
        setAuthError(err.message || 'Ошибка авторизации')
        setAuthState('no_telegram')
      })
  }, [])

  if (authState === 'loading') {
    return (
      <div className="h-full flex items-center justify-center"
        style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}>
        <div className="text-[15px]" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
          Авторизация...
        </div>
      </div>
    )
  }

  if (authState === 'no_telegram') {
    return (
      <div className="h-full flex flex-col items-center justify-center px-8 text-center gap-4"
        style={{ color: 'var(--tg-theme-text-color, #000)', backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}>
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.4 }}>
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
        </svg>
        <h1 className="text-xl font-bold">Flibusta</h1>
        <p className="text-[15px] leading-relaxed" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
          {authError || 'Откройте это приложение через Telegram бота для авторизации.'}
        </p>
      </div>
    )
  }

  const isDetailPage = location.pathname.startsWith('/book/') || location.pathname.startsWith('/audiobook/')

  return (
    <div className="h-full flex flex-col bg-tg-bg">
      <div className="flex-1 overflow-hidden relative">
        <Routes location={location}>
          <Route path="/" element={<Navigate to="/search" replace />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/audiobooks" element={<AudiobooksPage />} />
          <Route path="/audiobook/:topicId" element={<AudiobookDetailPage />} />
          <Route path="/downloads" element={<DownloadsPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/book/:id" element={<BookDetailPage />} />
        </Routes>
      </div>
      {!isDetailPage && (
        <>
          <MiniPlayer onExpand={() => setPlayerOpen(true)} />
          <BottomNav />
        </>
      )}
      <AudioPlayer open={playerOpen} onClose={() => setPlayerOpen(false)} />
    </div>
  )
}
