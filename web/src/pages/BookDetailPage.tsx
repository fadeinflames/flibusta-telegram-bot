import { useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '../api/client'
import { useBackButton, useHaptic } from '../hooks/useTelegram'
import { detailVariants, detailTransition, staggerContainer, staggerItem } from '../lib/animations'
import type { BookDetail, BookBrief } from '../api/types'
import BottomSheet from '../components/ui/BottomSheet'

const SHELF_OPTIONS = [
  { key: 'want', label: '📕 Хочу прочитать' },
  { key: 'reading', label: '📗 Читаю' },
  { key: 'done', label: '📘 Прочитано' },
  { key: 'recommend', label: '📙 Рекомендую' },
]

export default function BookDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { impact, notification } = useHaptic()
  const [showShelfPicker, setShowShelfPicker] = useState(false)
  const [showFullAnnotation, setShowFullAnnotation] = useState(false)

  const goBack = useCallback(() => navigate(-1), [navigate])
  useBackButton(goBack)

  const book = useQuery<BookDetail>({
    queryKey: ['book', id],
    queryFn: () => api.getBook(id!) as Promise<BookDetail>,
    enabled: !!id,
  })

  const related = useQuery<BookBrief[]>({
    queryKey: ['related', id],
    queryFn: () => api.getRelatedBooks(id!) as Promise<BookBrief[]>,
    enabled: !!id,
  })

  const toggleFavorite = useMutation({
    mutationFn: async () => {
      if (book.data?.is_favorite) {
        await api.removeFromLibrary(id!)
      } else {
        await api.addToLibrary(id!, {
          title: book.data!.title,
          author: book.data!.author,
          shelf: 'want',
        })
      }
    },
    onSuccess: () => {
      notification('success')
      queryClient.invalidateQueries({ queryKey: ['book', id] })
      queryClient.invalidateQueries({ queryKey: ['library'] })
      queryClient.invalidateQueries({ queryKey: ['library-counts'] })
    },
  })

  const changeShelf = useMutation({
    mutationFn: async (shelf: string) => {
      if (!book.data?.is_favorite) {
        await api.addToLibrary(id!, {
          title: book.data!.title,
          author: book.data!.author,
          shelf,
        })
      } else {
        await api.updateLibraryItem(id!, { shelf })
      }
    },
    onSuccess: () => {
      notification('success')
      setShowShelfPicker(false)
      queryClient.invalidateQueries({ queryKey: ['book', id] })
      queryClient.invalidateQueries({ queryKey: ['library'] })
      queryClient.invalidateQueries({ queryKey: ['library-counts'] })
    },
  })

  const handleDownload = (format: string) => {
    impact('medium')
    const formatKey = format.replace(/[()]/g, '')
    const url = api.getDownloadUrl(id!, formatKey)
    const initData = window.Telegram?.WebApp?.initData || ''
    window.open(`${url}?auth=${encodeURIComponent(initData)}`, '_blank')
  }

  if (book.isLoading) {
    return (
      <motion.div
        variants={detailVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={detailTransition}
        className="h-full"
        style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}
      >
        <div className="page-scroll" style={{ paddingBottom: 0 }}>
          <div className="h-[280px] skeleton-shimmer" />
          <div className="p-4 space-y-3">
            <div className="h-6 w-3/4 rounded-ios skeleton-shimmer" />
            <div className="h-4 w-1/2 rounded-ios skeleton-shimmer" />
            <div className="h-24 w-full rounded-ios skeleton-shimmer mt-4" />
          </div>
        </div>
      </motion.div>
    )
  }

  if (!book.data) {
    return (
      <motion.div
        variants={detailVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={detailTransition}
        className="h-full flex items-center justify-center"
        style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}
      >
        <p style={{ color: 'var(--tg-theme-hint-color)' }}>Книга не найдена</p>
      </motion.div>
    )
  }

  const b = book.data
  const formats = Object.keys(b.formats)
  const annotation = b.annotation || ''
  const shortAnnotation = annotation.length > 200 ? annotation.slice(0, 200) + '...' : annotation

  return (
    <motion.div
      variants={detailVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={detailTransition}
      className="h-full"
      style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}
    >
      <div className="page-scroll" style={{ paddingBottom: '24px' }}>
        {/* Hero cover area with parallax-like blur */}
        <div
          className="relative h-[280px] flex items-end justify-center overflow-hidden"
          style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
        >
          {b.cover && (
            <div
              className="absolute inset-0"
              style={{
                backgroundImage: `url(${b.cover})`,
                backgroundSize: 'cover',
                backgroundPosition: 'center',
                filter: 'blur(30px) brightness(0.7)',
                transform: 'scale(1.2)',
              }}
            />
          )}
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', damping: 20, stiffness: 200, delay: 0.15 }}
            className="relative z-10 pb-6"
          >
            {b.cover ? (
              <img
                src={b.cover}
                alt={b.title}
                className="h-[180px] rounded-[10px] shadow-float ring-1 ring-black/5"
                style={{ aspectRatio: '2/3', objectFit: 'cover' }}
              />
            ) : (
              <div
                className="h-[180px] w-[120px] rounded-[10px] flex items-center justify-center text-5xl shadow-float"
                style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)' }}
              >
                📖
              </div>
            )}
          </motion.div>
        </div>

        {/* Book info */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.2 }}
          className="px-4 pt-4"
        >
          <h1
            className="text-[22px] font-bold leading-tight text-center"
            style={{ color: 'var(--tg-theme-text-color, #000)' }}
          >
            {b.title}
          </h1>
          <p
            className="text-[15px] text-center mt-1"
            style={{ color: 'var(--tg-theme-link-color, #2481cc)' }}
          >
            {b.author}
          </p>

          {/* Metadata pills */}
          <div className="flex flex-wrap justify-center gap-2 mt-3">
            {b.year && (
              <span className="px-2.5 py-1 rounded-full text-[12px] glass-border"
                style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)', color: 'var(--tg-theme-subtitle-text-color, #6d6d72)' }}>
                {b.year}
              </span>
            )}
            {b.series && (
              <span className="px-2.5 py-1 rounded-full text-[12px] glass-border"
                style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)', color: 'var(--tg-theme-subtitle-text-color, #6d6d72)' }}>
                {b.series}
              </span>
            )}
            {b.size && (
              <span className="px-2.5 py-1 rounded-full text-[12px] glass-border"
                style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)', color: 'var(--tg-theme-subtitle-text-color, #6d6d72)' }}>
                {b.size}
              </span>
            )}
          </div>

          {/* Genre pills with accent color */}
          {b.genres.length > 0 && (
            <div className="flex flex-wrap justify-center gap-1.5 mt-3">
              {b.genres.map((g, i) => (
                <span key={i} className="px-2.5 py-0.5 rounded-full text-[11px] font-medium"
                  style={{
                    backgroundColor: 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 12%, transparent)',
                    color: 'var(--tg-theme-button-color, #2481cc)',
                  }}>
                  {g}
                </span>
              ))}
            </div>
          )}
        </motion.div>

        {/* Action buttons — sticky glass bar */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.3 }}
          className="flex gap-3 px-4 mt-5"
        >
          <motion.button
            whileTap={{ scale: 0.96 }}
            onClick={() => toggleFavorite.mutate()}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-ios-lg text-[15px] font-medium transition-all glass-border"
            style={{
              backgroundColor: b.is_favorite
                ? 'color-mix(in srgb, var(--tg-theme-destructive-text-color, #ff3b30) 12%, transparent)'
                : 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 12%, transparent)',
              color: b.is_favorite
                ? 'var(--tg-theme-destructive-text-color, #ff3b30)'
                : 'var(--tg-theme-button-color, #2481cc)',
            }}
          >
            {b.is_favorite ? '★ В библиотеке' : '☆ В библиотеку'}
          </motion.button>

          <motion.button
            whileTap={{ scale: 0.93 }}
            onClick={() => {
              impact('light')
              setShowShelfPicker(true)
            }}
            className="flex items-center justify-center w-12 py-3 rounded-ios-lg glass-border"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
              color: 'var(--tg-theme-text-color, #000)',
            }}
          >
            📚
          </motion.button>
        </motion.div>

        {/* Download formats */}
        {formats.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.35 }}
            className="px-4 mt-5"
          >
            <p
              className="text-[13px] font-semibold uppercase tracking-wider mb-2.5"
              style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}
            >
              Скачать
            </p>
            <div className="flex flex-wrap gap-2">
              {formats.map((fmt) => (
                <motion.button
                  key={fmt}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => handleDownload(fmt)}
                  className="px-4 py-2.5 rounded-ios text-[14px] font-semibold shadow-sm"
                  style={{
                    backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
                    color: 'var(--tg-theme-button-text-color, #fff)',
                  }}
                >
                  {fmt}
                </motion.button>
              ))}
            </div>
          </motion.div>
        )}

        {/* Annotation */}
        {annotation && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.4 }}
            className="px-4 mt-5"
          >
            <p
              className="text-[13px] font-semibold uppercase tracking-wider mb-2.5"
              style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}
            >
              Описание
            </p>
            <p
              className="text-[14px] leading-relaxed"
              style={{ color: 'var(--tg-theme-text-color, #000)' }}
            >
              {showFullAnnotation ? annotation : shortAnnotation}
            </p>
            {annotation.length > 200 && (
              <button
                onClick={() => setShowFullAnnotation(!showFullAnnotation)}
                className="text-[13px] font-medium mt-1.5"
                style={{ color: 'var(--tg-theme-link-color, #2481cc)' }}
              >
                {showFullAnnotation ? 'Свернуть' : 'Читать далее'}
              </button>
            )}
          </motion.div>
        )}

        {/* Related books */}
        {related.data && related.data.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.45 }}
            className="mt-5"
          >
            <p
              className="px-4 text-[13px] font-semibold uppercase tracking-wider mb-2.5"
              style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}
            >
              Ещё у автора
            </p>
            <motion.div
              variants={staggerContainer}
              initial="hidden"
              animate="show"
              className="flex gap-3 px-4 overflow-x-auto no-scrollbar pb-2"
            >
              {related.data.map((rb: BookBrief) => (
                <motion.button
                  key={rb.id}
                  variants={staggerItem}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => {
                    impact('light')
                    navigate(`/book/${rb.id}`)
                  }}
                  className="flex-shrink-0 w-[100px]"
                >
                  <div
                    className="w-[100px] h-[140px] rounded-[10px] overflow-hidden mb-1.5 shadow-md ring-1 ring-black/5"
                    style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
                  >
                    {rb.cover ? (
                      <img src={rb.cover} alt={rb.title} className="w-full h-full object-cover" loading="lazy" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-3xl opacity-30">📖</div>
                    )}
                  </div>
                  <p
                    className="text-[12px] leading-tight line-clamp-2"
                    style={{ color: 'var(--tg-theme-text-color, #000)' }}
                  >
                    {rb.title}
                  </p>
                </motion.button>
              ))}
            </motion.div>
          </motion.div>
        )}
      </div>

      {/* Shelf picker — reusable BottomSheet */}
      <BottomSheet open={showShelfPicker} onClose={() => setShowShelfPicker(false)} title="Выбрать полку">
        <div className="space-y-1">
          {SHELF_OPTIONS.map(opt => (
            <motion.button
              key={opt.key}
              whileTap={{ scale: 0.97 }}
              onClick={() => changeShelf.mutate(opt.key)}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-ios text-left transition-colors"
              style={{
                backgroundColor: b.shelf === opt.key
                  ? 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 12%, transparent)'
                  : 'transparent',
                color: 'var(--tg-theme-text-color, #000)',
              }}
            >
              <span className="text-[18px]">{opt.label.split(' ')[0]}</span>
              <span className="text-[15px]">{opt.label.split(' ').slice(1).join(' ')}</span>
              {b.shelf === opt.key && (
                <span className="ml-auto" style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}>✓</span>
              )}
            </motion.button>
          ))}

          {b.is_favorite && (
            <>
              <div className="separator my-2" />
              <motion.button
                whileTap={{ scale: 0.97 }}
                onClick={() => { toggleFavorite.mutate(); setShowShelfPicker(false) }}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-ios text-left"
                style={{ color: 'var(--tg-theme-destructive-text-color, #ff3b30)' }}
              >
                Удалить из библиотеки
              </motion.button>
            </>
          )}
        </div>
      </BottomSheet>
    </motion.div>
  )
}
