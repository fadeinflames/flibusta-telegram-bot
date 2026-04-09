/**
 * App — mirrors time_jedi_bot/web/frontend/src/App.tsx
 *
 * - PublicRoute: only accessible when NOT authenticated (login page)
 * - ProtectedRoute: requires auth, redirects to /login otherwise
 * - Layout: shell with BottomNav + MiniPlayer
 */

import { useState } from 'react'
import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './store/auth'
import { useTelegram } from './hooks/useTelegram'
import BottomNav from './components/layout/BottomNav'
import MiniPlayer from './components/audio/MiniPlayer'
import AudioPlayer from './components/audio/AudioPlayer'
import LoginPage from './pages/LoginPage'
import LibraryPage from './pages/LibraryPage'
import SearchPage from './pages/SearchPage'
import AudiobooksPage from './pages/AudiobooksPage'
import AudiobookDetailPage from './pages/AudiobookDetailPage'
import DownloadsPage from './pages/DownloadsPage'
import ProfilePage from './pages/ProfilePage'
import BookDetailPage from './pages/BookDetailPage'

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth()
  if (isAuthenticated) return <Navigate to="/" replace />
  return <>{children}</>
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth()
  const location = useLocation()
  if (!isAuthenticated) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

function Layout() {
  const location = useLocation()
  const [playerOpen, setPlayerOpen] = useState(false)
  const isDetailPage = location.pathname.startsWith('/book/') || location.pathname.startsWith('/audiobook/')

  return (
    <div className="h-full bg-tg-bg">
      {/* Page content takes full height, page-scroll handles its own padding-bottom */}
      <Outlet />
      {!isDetailPage && (
        <div className="fixed bottom-0 left-0 right-0 z-40">
          <MiniPlayer onExpand={() => setPlayerOpen(true)} />
          <BottomNav />
        </div>
      )}
      <AudioPlayer open={playerOpen} onClose={() => setPlayerOpen(false)} />
    </div>
  )
}

export default function App() {
  useTelegram()

  return (
    <Routes>
      <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
      <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<Navigate to="/search" replace />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="audiobooks" element={<AudiobooksPage />} />
        <Route path="audiobook/:topicId" element={<AudiobookDetailPage />} />
        <Route path="downloads" element={<DownloadsPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="book/:id" element={<BookDetailPage />} />
      </Route>
    </Routes>
  )
}
