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

  const emptyMessages: Record<ShelfKey, string> = {
    all: 'Ваша библиотека пока пуста',
    want: 'Нет книг в списке желаний',
    reading: 'Вы ещё не начали ничего читать',
    done: 'Нет прочитанных книг',
    recommend: 'Нет рекомендаций',
  }

  return (
    <motion.div
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={pageTransition}
      className="h-full flex flex-col"
    >
      <div className="px-4 pt-4 pb-1">
        <h1 className="text-[34px] font-bold tracking-tight" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
          Библиотека
        </h1>
      </div>

      <ShelfFilter active={shelf} counts={counts.data} onChange={handleShelfChange} />

      <div className="page-scroll">
        {library.isLoading && !library.isError && !library.failureCount ? (
          <div>
            {[...Array(5)].map((_, i) => <SkeletonCard key={i} delay={i * 60} />)}
          </div>
        ) : !library.data?.items?.length ? (
          <EmptyState
            icon="📚"
            title={emptyMessages[shelf]}
            subtitle="Найдите книгу через поиск и добавьте в библиотеку"
          />
        ) : (
          <>
            <motion.div variants={staggerContainer} initial="hidden" animate="show">
              {library.data.items.map((item: FavoriteItem) => (
                <motion.div key={item.book_id} variants={staggerItem}>
                  <BookCard
                    id={item.book_id}
                    title={item.title}
                    author={item.author}
                    shelf={item.shelf}
                  />
                  <div className="separator mx-4" />
                </motion.div>
              ))}
            </motion.div>

            {totalPages > 1 && <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />}
          </>
        )}
      </div>
    </motion.div>
  )
}

function Pagination({ page, totalPages, onPageChange }: { page: number; totalPages: number; onPageChange: (p: number) => void }) {
  return (
    <div className="flex justify-center items-center gap-4 py-5">
      <PaginationButton label="Назад" disabled={page <= 1} onClick={() => onPageChange(page - 1)} />
      <span className="text-[13px] font-medium" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
        {page} / {totalPages}
      </span>
      <PaginationButton label="Далее" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)} />
    </div>
  )
}

function PaginationButton({ label, disabled, onClick }: { label: string; disabled: boolean; onClick: () => void }) {
  return (
    <motion.button
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
      disabled={disabled}
      className="px-4 py-2 rounded-full text-[13px] font-semibold disabled:opacity-25 transition-opacity"
      style={{
        backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
        color: 'var(--tg-theme-text-color, #000)',
      }}
    >
      {label}
    </motion.button>
  )
}
