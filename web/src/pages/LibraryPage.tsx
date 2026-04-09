import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '../api/client'
import type { ShelfKey, ShelfCounts, PaginatedResponse, FavoriteItem } from '../api/types'
import { pageVariants, pageTransition, staggerContainer, staggerItem } from '../lib/animations'
import ShelfFilter from '../components/books/ShelfFilter'
import BookCard from '../components/books/BookCard'
import SkeletonCard from '../components/books/SkeletonCard'
import EmptyState from '../components/ui/EmptyState'

const SHELF_EMPTY: Record<ShelfKey, { icon: string; title: string; subtitle: string }> = {
  all: { icon: '📚', title: 'Ваша библиотека пока пуста', subtitle: 'Найдите книгу через поиск и добавьте её сюда' },
  want: { icon: '📕', title: 'Нет книг в списке желаний', subtitle: 'Добавляйте книги, которые хотите прочитать' },
  reading: { icon: '📗', title: 'Вы ещё ничего не читаете', subtitle: 'Начните читать книгу из вашей библиотеки' },
  done: { icon: '📘', title: 'Нет прочитанных книг', subtitle: 'Завершённые книги появятся здесь' },
  recommend: { icon: '📙', title: 'Нет рекомендаций', subtitle: 'Рекомендуйте книги, которые понравились' },
}

export default function LibraryPage() {
  const [shelf, setShelf] = useState<ShelfKey>('all')
  const [page, setPage] = useState(1)

  const counts = useQuery<ShelfCounts>({
    queryKey: ['library-counts'],
    queryFn: () => api.getShelfCounts() as Promise<ShelfCounts>,
  })

  const library = useQuery<PaginatedResponse<FavoriteItem>>({
    queryKey: ['library', shelf, page],
    queryFn: () => api.getLibrary(shelf, page) as Promise<PaginatedResponse<FavoriteItem>>,
  })

  const handleShelfChange = (newShelf: ShelfKey) => {
    setShelf(newShelf)
    setPage(1)
  }

  const totalPages = library.data ? Math.ceil(library.data.total / library.data.per_page) : 0
  const emptyState = SHELF_EMPTY[shelf]

  return (
    <motion.div
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={pageTransition}
      className="h-full flex flex-col"
    >
      {/* Header */}
      <div className="px-5 pt-4 pb-1">
        <h1
          className="text-[34px] font-bold tracking-tight"
          style={{ color: 'var(--tg-theme-text-color, #000)' }}
        >
          Библиотека
        </h1>
      </div>

      <ShelfFilter active={shelf} counts={counts.data} onChange={handleShelfChange} />

      <div className="page-scroll">
        {library.isLoading && !library.isError && !library.failureCount ? (
          <div className="px-1">
            {[...Array(5)].map((_, i) => <SkeletonCard key={i} delay={i * 60} />)}
          </div>
        ) : !library.data?.items?.length ? (
          <EmptyState
            icon={emptyState.icon}
            title={emptyState.title}
            subtitle={emptyState.subtitle}
          />
        ) : (
          <>
            <motion.div variants={staggerContainer} initial="hidden" animate="show">
              {library.data.items.map((item: FavoriteItem) => (
                <motion.div key={item.book_id} variants={staggerItem}>
                  <BookCard
                    id={item.book_id}
                    title={item.title.replace(/\s*\([a-z0-9]+\)\s*$/i, '')}
                    author={item.author}
                    cover={item.cover}
                    shelf={item.shelf}
                  />
                  <div
                    className="mx-5 h-px"
                    style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)' }}
                  />
                </motion.div>
              ))}
            </motion.div>

            {totalPages > 1 && (
              <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
            )}
          </>
        )}
      </div>
    </motion.div>
  )
}

function Pagination({ page, totalPages, onPageChange }: { page: number; totalPages: number; onPageChange: (p: number) => void }) {
  return (
    <div className="flex justify-center items-center gap-3 py-6 px-5">
      <motion.button
        whileTap={{ scale: 0.94 }}
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        className="w-10 h-10 rounded-full flex items-center justify-center disabled:opacity-20 transition-opacity"
        style={{
          backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
          color: 'var(--tg-theme-text-color, #000)',
        }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </motion.button>

      <div className="flex items-center gap-1.5">
        {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
          let pageNum: number
          if (totalPages <= 5) {
            pageNum = i + 1
          } else if (page <= 3) {
            pageNum = i + 1
          } else if (page >= totalPages - 2) {
            pageNum = totalPages - 4 + i
          } else {
            pageNum = page - 2 + i
          }

          const isActive = pageNum === page
          return (
            <motion.button
              key={pageNum}
              whileTap={{ scale: 0.9 }}
              onClick={() => onPageChange(pageNum)}
              className="w-9 h-9 rounded-full flex items-center justify-center text-[14px] font-semibold transition-all duration-200"
              style={{
                backgroundColor: isActive
                  ? 'var(--tg-theme-button-color, #2481cc)'
                  : 'transparent',
                color: isActive
                  ? 'var(--tg-theme-button-text-color, #fff)'
                  : 'var(--tg-theme-hint-color, #999)',
              }}
            >
              {pageNum}
            </motion.button>
          )
        })}
      </div>

      <motion.button
        whileTap={{ scale: 0.94 }}
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        className="w-10 h-10 rounded-full flex items-center justify-center disabled:opacity-20 transition-opacity"
        style={{
          backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
          color: 'var(--tg-theme-text-color, #000)',
        }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9 18l6-6-6-6" />
        </svg>
      </motion.button>
    </div>
  )
}
