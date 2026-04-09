import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '../api/client'
import { useHaptic } from '../hooks/useTelegram'
import type { PaginatedResponse, DownloadItem } from '../api/types'
import { pageVariants, pageTransition, staggerContainer, staggerItem } from '../lib/animations'
import BookCard from '../components/books/BookCard'
import SkeletonCard from '../components/books/SkeletonCard'
import EmptyState from '../components/ui/EmptyState'

function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000)
  if (diffDays === 0) return 'Сегодня'
  if (diffDays === 1) return 'Вчера'
  if (diffDays < 7) return `${diffDays} дн. назад`
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
}

function groupByDate(items: DownloadItem[]): Map<string, DownloadItem[]> {
  const groups = new Map<string, DownloadItem[]>()
  for (const item of items) {
    const key = formatDate(item.download_date)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(item)
  }
  return groups
}

export default function DownloadsPage() {
  const [page, setPage] = useState(1)
  const queryClient = useQueryClient()
  const { notification } = useHaptic()

  const downloads = useQuery<PaginatedResponse<DownloadItem>>({
    queryKey: ['downloads', page],
    queryFn: () => api.getDownloads(page) as Promise<PaginatedResponse<DownloadItem>>,
  })

  const handleClear = async () => {
    await api.clearDownloads()
    notification('success')
    queryClient.invalidateQueries({ queryKey: ['downloads'] })
  }

  const items = downloads.data?.items || []
  const grouped = groupByDate(items)

  return (
    <motion.div
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={pageTransition}
      className="h-full flex flex-col"
    >
      <div className="px-4 pt-4 pb-1 flex items-end justify-between">
        <h1 className="text-[34px] font-bold tracking-tight" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
          Загрузки
        </h1>
        {items.length > 0 && (
          <motion.button whileTap={{ scale: 0.95 }} onClick={handleClear}
            className="text-[14px] font-medium mb-1.5" style={{ color: 'var(--tg-theme-destructive-text-color, #ff3b30)' }}>
            Очистить
          </motion.button>
        )}
      </div>

      <div className="page-scroll">
        {downloads.isLoading && !downloads.failureCount ? (
          <div>{[...Array(5)].map((_, i) => <SkeletonCard key={i} delay={i * 60} />)}</div>
        ) : items.length === 0 ? (
          <EmptyState icon="📥" title="Нет загрузок" subtitle="Скачанные книги будут отображаться здесь" />
        ) : (
          <motion.div variants={staggerContainer} initial="hidden" animate="show">
            {Array.from(grouped.entries()).map(([date, groupItems]) => (
              <div key={date}>
                <p className="px-4 pt-4 pb-1 text-[13px] font-semibold uppercase tracking-wider"
                  style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}>
                  {date}
                </p>
                {groupItems.map((item, i) => (
                  <motion.div key={`${item.book_id}-${i}`} variants={staggerItem}>
                    <BookCard id={item.book_id} title={item.title} author={item.author} subtitle={item.format.toUpperCase()} />
                    <div className="separator mx-4" />
                  </motion.div>
                ))}
              </div>
            ))}
          </motion.div>
        )}
      </div>
    </motion.div>
  )
}
