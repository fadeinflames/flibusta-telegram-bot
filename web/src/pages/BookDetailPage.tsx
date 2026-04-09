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
  { key: 'want', label: 'Хочу прочитать', icon: '📕' },
  { key: 'reading', label: 'Читаю', icon: '📗' },
  { key: 'done', label: 'Прочитано', icon: '📘' },
  { key: 'recommend', label: 'Рекомендую', icon: '📙' },
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
    window.open(url, '_blank')
  }

  if (book.isLoading) {
    return (
      <motion.div
        variants={detailVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={detailTransition}
        className="h-full flex flex-col"
        style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}
      >
        <div className="page-scroll" style={{ paddingBottom: 0 }}>
          <div className="h-[320px] skeleton-shimmer" />
          <div className="p-5 space-y-3">
            <div className="h-7 w-3/4 rounded-2xl skeleton-shimmer mx-auto" />
            <div className="h-5 w-1/2 rounded-2xl skeleton-shimmer mx-auto" />
            <div className="flex justify-center gap-2 mt-4">
              <div className="h-8 w-16 rounded-full skeleton-shimmer" />
              <div className="h-8 w-16 rounded-full skeleton-shimmer" />
            </div>
            <div className="h-28 w-full rounded-2xl skeleton-shimmer mt-4" />
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
        <div className="text-center px-8">
          <div className="text-[48px] mb-3 opacity-40">📖</div>
          <p className="text-[17px] font-semibold" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
            Книга не найдена
          </p>
          <p className="text-[14px] mt-1" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
            Возможно, она была удалена
          </p>
        </div>
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
      className="h-full flex flex-col"
      style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}
    >
      <div className="page-scroll" style={{ paddingBottom: '32px' }}>
        {/* Hero with gradient overlay on blurred cover */}
        <div className="relative h-[320px] flex items-end justify-center overflow-hidden">
          {b.cover ? (
            <div
              className="absolute inset-0"
              style={{
                backgroundImage: `url(${b.cover})`,
                backgroundSize: 'cover',
                backgroundPosition: 'center',
                filter: 'blur(40px) saturate(1.5) brightness(0.6)',
                transform: 'scale(1.3)',
              }}
            />
          ) : (
            <div
              className="absolute inset-0"
              style={{
                background: 'linear-gradient(145deg, var(--tg-theme-button-color, #2481cc), color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 50%, #6366f1))',
              }}
            />
          )}
          {/* Gradient fade to page background */}
          <div
            className="absolute inset-0"
            style={{
              background: 'linear-gradient(to bottom, transparent 40%, var(--tg-theme-bg-color, #fff) 100%)',
            }}
          />

          {/* Frosted back button */}
          <button
            onClick={goBack}
            className="absolute top-4 left-4 z-20 w-10 h-10 rounded-full flex items-center justify-center"
            style={{
              backgroundColor: 'rgba(255,255,255,0.18)',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              border: '1px solid rgba(255,255,255,0.2)',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>

          {/* Floating cover */}
          <motion.div
            initial={{ scale: 0.85, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 180, delay: 0.1 }}
            className="relative z-10 pb-4"
          >
            {b.cover ? (
              <div className="relative">
                <img
                  src={b.cover}
                  alt={b.title}
                  className="h-[200px] rounded-2xl"
                  style={{
                    aspectRatio: '2/3',
                    objectFit: 'cover',
                    boxShadow: '0 20px 60px rgba(0,0,0,0.4), 0 8px 20px rgba(0,0,0,0.2)',
                  }}
                />
                <div
                  className="absolute inset-0 rounded-2xl pointer-events-none"
                  style={{
                    background: 'linear-gradient(135deg, rgba(255,255,255,0.15) 0%, transparent 50%)',
                  }}
                />
              </div>
            ) : (
              <div
                className="h-[200px] w-[133px] rounded-2xl flex items-center justify-center text-[56px]"
                style={{
                  backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                  boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
                }}
              >
                📖
              </div>
            )}
          </motion.div>
        </div>

        {/* Title and author */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.2 }}
          className="px-5 pt-2"
        >
          <h1
            className="text-[24px] font-bold leading-tight text-center tracking-tight"
            style={{ color: 'var(--tg-theme-text-color, #000)' }}
          >
            {b.title}
          </h1>
          <p
            className="text-[16px] text-center mt-1.5 font-medium"
            style={{ color: 'var(--tg-theme-link-color, #2481cc)' }}
          >
            {b.author}
          </p>

          {/* Metadata pills */}
          <div className="flex flex-wrap justify-center gap-2 mt-4">
            {b.year && (
              <span
                className="px-3 py-1.5 rounded-full text-[12px] font-medium"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)',
                  color: 'var(--tg-theme-subtitle-text-color, #6d6d72)',
                }}
              >
                {b.year}
              </span>
            )}
            {b.series && (
              <span
                className="px-3 py-1.5 rounded-full text-[12px] font-medium"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)',
                  color: 'var(--tg-theme-subtitle-text-color, #6d6d72)',
                }}
              >
                {b.series}
              </span>
            )}
            {b.size && (
              <span
                className="px-3 py-1.5 rounded-full text-[12px] font-medium"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)',
                  color: 'var(--tg-theme-subtitle-text-color, #6d6d72)',
                }}
              >
                {b.size}
              </span>
            )}
          </div>

          {/* Genre tags */}
          {b.genres.length > 0 && (
            <div className="flex flex-wrap justify-center gap-1.5 mt-3">
              {b.genres.map((g, i) => (
                <span
                  key={i}
                  className="px-3 py-1 rounded-full text-[11px] font-semibold"
                  style={{
                    backgroundColor: 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 10%, transparent)',
                    color: 'var(--tg-theme-button-color, #2481cc)',
                  }}
                >
                  {g}
                </span>
              ))}
            </div>
          )}
        </motion.div>

        {/* Action buttons */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.3 }}
          className="flex gap-3 px-5 mt-6"
        >
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={() => toggleFavorite.mutate()}
            className="flex-1 flex items-center justify-center gap-2.5 py-3.5 rounded-2xl text-[15px] font-semibold transition-all"
            style={{
              backgroundColor: b.is_favorite
                ? 'color-mix(in srgb, var(--tg-theme-destructive-text-color, #ff3b30) 10%, transparent)'
                : 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 10%, transparent)',
              color: b.is_favorite
                ? 'var(--tg-theme-destructive-text-color, #ff3b30)'
                : 'var(--tg-theme-button-color, #2481cc)',
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill={b.is_favorite ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
            </svg>
            {b.is_favorite ? 'В библиотеке' : 'В библиотеку'}
          </motion.button>

          <motion.button
            whileTap={{ scale: 0.92 }}
            onClick={() => {
              impact('light')
              setShowShelfPicker(true)
            }}
            className="flex items-center justify-center w-[52px] py-3.5 rounded-2xl"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
              color: 'var(--tg-theme-text-color, #000)',
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
              <line x1="9" y1="7" x2="15" y2="7" />
            </svg>
          </motion.button>
        </motion.div>

        {/* Download format cards */}
        {formats.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.35 }}
            className="px-5 mt-6"
          >
            <p
              className="text-[13px] font-semibold uppercase tracking-wider mb-3"
              style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}
            >
              Скачать
            </p>
            <div className="grid grid-cols-3 gap-2.5">
              {formats.map((fmt) => (
                <motion.button
                  key={fmt}
                  whileTap={{ scale: 0.93 }}
                  onClick={() => handleDownload(fmt)}
                  className="flex flex-col items-center gap-1.5 py-4 rounded-2xl"
                  style={{
                    backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
                  }}
                >
                  <svg
                    width="22" height="22" viewBox="0 0 24 24" fill="none"
                    stroke="var(--tg-theme-button-color, #2481cc)"
                    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
                  >
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                    <polyline points="7,10 12,15 17,10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                  <span
                    className="text-[13px] font-bold uppercase"
                    style={{ color: 'var(--tg-theme-text-color, #000)' }}
                  >
                    {fmt}
                  </span>
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
            className="px-5 mt-6"
          >
            <p
              className="text-[13px] font-semibold uppercase tracking-wider mb-3"
              style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}
            >
              Описание
            </p>
            <div
              className="p-4 rounded-2xl"
              style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)' }}
            >
              <p
                className="text-[14px] leading-[1.65]"
                style={{ color: 'var(--tg-theme-text-color, #000)' }}
              >
                {showFullAnnotation ? annotation : shortAnnotation}
              </p>
              {annotation.length > 200 && (
                <button
                  onClick={() => setShowFullAnnotation(!showFullAnnotation)}
                  className="text-[14px] font-semibold mt-2 block"
                  style={{ color: 'var(--tg-theme-link-color, #2481cc)' }}
                >
                  {showFullAnnotation ? 'Свернуть' : 'Читать далее'}
                </button>
              )}
            </div>
          </motion.div>
        )}

        {/* Related books horizontal scroll */}
        {related.data && related.data.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 240, delay: 0.45 }}
            className="mt-6"
          >
            <p
              className="px-5 text-[13px] font-semibold uppercase tracking-wider mb-3"
              style={{ color: 'var(--tg-theme-section-header-text-color, #6d6d72)' }}
            >
              Ещё у автора
            </p>
            <motion.div
              variants={staggerContainer}
              initial="hidden"
              animate="show"
              className="flex gap-3 px-5 overflow-x-auto no-scrollbar pb-2"
            >
              {related.data.map((rb: BookBrief) => (
                <motion.button
                  key={rb.id}
                  variants={staggerItem}
                  whileTap={{ scale: 0.94 }}
                  onClick={() => {
                    impact('light')
                    navigate(`/book/${rb.id}`)
                  }}
                  className="flex-shrink-0 w-[110px]"
                >
                  <div
                    className="w-[110px] h-[154px] rounded-2xl overflow-hidden mb-2"
                    style={{
                      backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
                      boxShadow: '0 4px 16px rgba(0,0,0,0.1)',
                    }}
                  >
                    {rb.cover ? (
                      <img src={rb.cover} alt={rb.title} className="w-full h-full object-cover" loading="lazy" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-3xl opacity-25">📖</div>
                    )}
                  </div>
                  <p
                    className="text-[13px] font-medium leading-tight line-clamp-2"
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

      {/* Shelf picker bottom sheet */}
      <BottomSheet open={showShelfPicker} onClose={() => setShowShelfPicker(false)} title="Выбрать полку">
        <div className="space-y-1 px-1">
          {SHELF_OPTIONS.map(opt => {
            const isActive = b.shelf === opt.key
            return (
              <motion.button
                key={opt.key}
                whileTap={{ scale: 0.97 }}
                onClick={() => changeShelf.mutate(opt.key)}
                className="w-full flex items-center gap-3.5 px-4 py-3.5 rounded-2xl text-left transition-colors"
                style={{
                  backgroundColor: isActive
                    ? 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 10%, transparent)'
                    : 'transparent',
                  color: 'var(--tg-theme-text-color, #000)',
                }}
              >
                <span className="text-[22px]">{opt.icon}</span>
                <span className="text-[16px] font-medium flex-1">{opt.label}</span>
                {isActive && (
                  <svg
                    width="20" height="20" viewBox="0 0 24 24" fill="none"
                    stroke="var(--tg-theme-button-color, #2481cc)"
                    strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </motion.button>
            )
          })}

          {b.is_favorite && (
            <>
              <div
                className="my-2 mx-4 h-px"
                style={{ backgroundColor: 'color-mix(in srgb, var(--tg-theme-text-color, #000) 8%, transparent)' }}
              />
              <motion.button
                whileTap={{ scale: 0.97 }}
                onClick={() => { toggleFavorite.mutate(); setShowShelfPicker(false) }}
                className="w-full flex items-center gap-3.5 px-4 py-3.5 rounded-2xl text-left"
                style={{ color: 'var(--tg-theme-destructive-text-color, #ff3b30)' }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                </svg>
                <span className="text-[16px] font-medium">Удалить из библиотеки</span>
              </motion.button>
            </>
          )}
        </div>
      </BottomSheet>
    </motion.div>
  )
}
