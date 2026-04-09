import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useLocation } from 'react-router-dom'
import { useTelegram } from './hooks/useTelegram'
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

export default function App() {
  useTelegram()
  const location = useLocation()
  const [playerOpen, setPlayerOpen] = useState(false)

  const isDetailPage = location.pathname.startsWith('/book/') || location.pathname.startsWith('/audiobook/')

  return (
    <div className="h-full flex flex-col bg-tg-bg">
      <div className="flex-1 overflow-hidden relative">
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            <Route path="/" element={<Navigate to="/library" replace />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/audiobooks" element={<AudiobooksPage />} />
            <Route path="/audiobook/:topicId" element={<AudiobookDetailPage />} />
            <Route path="/downloads" element={<DownloadsPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/book/:id" element={<BookDetailPage />} />
          </Routes>
        </AnimatePresence>
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
