import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '../api/client'
import { useBackButton } from '../hooks/useTelegram'
import type { BookDetail } from '../api/types'

/* ────── FB2 Parser ────── */

interface FB2Data {
  title: string
  author: string
  chapters: FB2Chapter[]
  images: Map<string, string> // id -> data:image/... URL
}

interface FB2Chapter {
  title: string
  html: string
}

function parseFB2(xml: string): FB2Data {
  const parser = new DOMParser()
  const doc = parser.parseFromString(xml, 'application/xml')

  // Extract images (binary elements)
  const images = new Map<string, string>()
  doc.querySelectorAll('binary').forEach((bin) => {
    const id = bin.getAttribute('id') || ''
    const contentType = bin.getAttribute('content-type') || 'image/jpeg'
    const base64 = (bin.textContent || '').replace(/\s/g, '')
    if (id && base64) {
      images.set(id, `data:${contentType};base64,${base64}`)
    }
  })

  // Extract title info
  const titleInfo = doc.querySelector('title-info')
  const bookTitle = titleInfo?.querySelector('book-title')?.textContent || ''
  const authorFirst = titleInfo?.querySelector('author first-name')?.textContent || ''
  const authorLast = titleInfo?.querySelector('author last-name')?.textContent || ''
  const author = [authorFirst, authorLast].filter(Boolean).join(' ')

  // Extract body sections
  const body = doc.querySelector('body')
  const chapters: FB2Chapter[] = []

  if (body) {
    const topSections = body.querySelectorAll(':scope > section')
    if (topSections.length > 0) {
      topSections.forEach((section) => {
        const chTitle = extractSectionTitle(section)
        const html = convertSectionToHtml(section, images)
        chapters.push({ title: chTitle || `Глава ${chapters.length + 1}`, html })
      })
    } else {
      // No sections — whole body is one chapter
      const html = convertNodeToHtml(body, images)
      chapters.push({ title: bookTitle || 'Текст', html })
    }
  }

  return { title: bookTitle, author, chapters, images }
}

function extractSectionTitle(section: Element): string {
  const titleEl = section.querySelector(':scope > title')
  if (!titleEl) return ''
  return (titleEl.textContent || '').trim().replace(/\s+/g, ' ')
}

function convertSectionToHtml(section: Element, images: Map<string, string>): string {
  const parts: string[] = []
  for (const child of Array.from(section.childNodes)) {
    if (child.nodeType === Node.ELEMENT_NODE) {
      const el = child as Element
      if (el.tagName === 'title') continue // already extracted
      parts.push(convertElementToHtml(el, images))
    }
  }
  return parts.join('\n')
}

function convertNodeToHtml(node: Element, images: Map<string, string>): string {
  const parts: string[] = []
  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType === Node.ELEMENT_NODE) {
      parts.push(convertElementToHtml(child as Element, images))
    }
  }
  return parts.join('\n')
}

function convertElementToHtml(el: Element, images: Map<string, string>): string {
  const tag = el.tagName.toLowerCase()

  switch (tag) {
    case 'p':
      return `<p>${inlineContent(el, images)}</p>`
    case 'empty-line':
      return '<br/>'
    case 'title':
      return `<h2>${inlineContent(el, images)}</h2>`
    case 'subtitle':
      return `<h3>${inlineContent(el, images)}</h3>`
    case 'epigraph':
      return `<blockquote class="fb2-epigraph">${convertNodeToHtml(el, images)}</blockquote>`
    case 'cite':
      return `<blockquote class="fb2-cite">${convertNodeToHtml(el, images)}</blockquote>`
    case 'poem':
      return `<div class="fb2-poem">${convertNodeToHtml(el, images)}</div>`
    case 'stanza':
      return `<div class="fb2-stanza">${convertNodeToHtml(el, images)}</div>`
    case 'v':
      return `<p class="fb2-verse">${inlineContent(el, images)}</p>`
    case 'text-author':
      return `<p class="fb2-text-author">${inlineContent(el, images)}</p>`
    case 'section':
      return `<div class="fb2-section">${convertNodeToHtml(el, images)}</div>`
    case 'image': {
      const href = el.getAttributeNS('http://www.w3.org/1999/xlink', 'href')
        || el.getAttribute('l:href')
        || el.getAttribute('xlink:href')
        || ''
      const imgId = href.replace('#', '')
      const src = images.get(imgId)
      if (src) return `<div class="fb2-image"><img src="${src}" alt="" /></div>`
      return ''
    }
    case 'table':
      return `<table class="fb2-table">${el.innerHTML}</table>`
    case 'annotation':
      return `<div class="fb2-annotation">${convertNodeToHtml(el, images)}</div>`
    default:
      return convertNodeToHtml(el, images)
  }
}

function inlineContent(el: Element, images: Map<string, string>): string {
  let result = ''
  for (const child of Array.from(el.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) {
      result += escapeHtml(child.textContent || '')
    } else if (child.nodeType === Node.ELEMENT_NODE) {
      const childEl = child as Element
      const tag = childEl.tagName.toLowerCase()
      switch (tag) {
        case 'strong':
          result += `<strong>${inlineContent(childEl, images)}</strong>`
          break
        case 'emphasis':
          result += `<em>${inlineContent(childEl, images)}</em>`
          break
        case 'strikethrough':
          result += `<s>${inlineContent(childEl, images)}</s>`
          break
        case 'a':
          result += `<span class="fb2-link">${inlineContent(childEl, images)}</span>`
          break
        case 'image': {
          const href = childEl.getAttributeNS('http://www.w3.org/1999/xlink', 'href')
            || childEl.getAttribute('l:href')
            || childEl.getAttribute('xlink:href')
            || ''
          const imgId = href.replace('#', '')
          const src = images.get(imgId)
          if (src) result += `<img src="${src}" class="fb2-inline-img" alt="" />`
          break
        }
        case 'p':
          result += `<p>${inlineContent(childEl, images)}</p>`
          break
        default:
          result += inlineContent(childEl, images)
      }
    }
  }
  return result
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/* ────── Reader Component ────── */

const FONT_SIZES = [14, 16, 18, 20, 22, 24]
const LINE_HEIGHTS = [1.4, 1.6, 1.8, 2.0]
const STORAGE_KEY = 'fb2_reader_settings'

type ReaderTheme = 'light' | 'sepia' | 'dark'
type FontFamily = 'system' | 'serif' | 'mono'

const THEME_STYLES: Record<ReaderTheme, { bg: string; text: string; accent: string; secondary: string }> = {
  light: { bg: '#ffffff', text: '#1a1a1a', accent: '#2481cc', secondary: '#f5f5f5' },
  sepia: { bg: '#f8f1e3', text: '#3d3229', accent: '#8b6914', secondary: '#efe6d5' },
  dark: { bg: '#1c1c1e', text: '#e5e5e7', accent: '#64a8e8', secondary: '#2c2c2e' },
}

const FONT_FAMILIES: Record<FontFamily, string> = {
  system: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', sans-serif",
  serif: "Georgia, 'Times New Roman', 'Noto Serif', serif",
  mono: "'SF Mono', 'Menlo', 'Courier New', monospace",
}

const FONT_FAMILY_LABELS: Record<FontFamily, string> = {
  system: 'Sans',
  serif: 'Serif',
  mono: 'Mono',
}

interface ReadingPosition {
  chapter: number
  scrollPercent: number
}

interface ReaderSettings {
  fontSize: number
  lineHeight: number
  fontFamily: FontFamily
  theme: ReaderTheme
  progress: Record<string, ReadingPosition>
}

function loadSettings(): ReaderSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      // Migrate old format (number -> ReadingPosition)
      if (parsed.progress) {
        for (const key of Object.keys(parsed.progress)) {
          if (typeof parsed.progress[key] === 'number') {
            parsed.progress[key] = { chapter: parsed.progress[key], scrollPercent: 0 }
          }
        }
      }
      return {
        fontSize: parsed.fontSize ?? 18,
        lineHeight: parsed.lineHeight ?? 1.8,
        fontFamily: parsed.fontFamily ?? 'system',
        theme: parsed.theme ?? 'light',
        progress: parsed.progress ?? {},
      }
    }
  } catch { /* ignore */ }
  return { fontSize: 18, lineHeight: 1.8, fontFamily: 'system', theme: 'light', progress: {} }
}

function saveSettings(settings: ReaderSettings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch { /* ignore */ }
}

export default function BookReaderPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const goBack = useCallback(() => navigate(-1), [navigate])
  useBackButton(goBack)

  const settings = useMemo(() => loadSettings(), [])
  const [fontSize, setFontSize] = useState(settings.fontSize)
  const [lineHeight, setLineHeight] = useState(settings.lineHeight)
  const [fontFamily, setFontFamily] = useState<FontFamily>(settings.fontFamily)
  const [readerTheme, setReaderTheme] = useState<ReaderTheme>(settings.theme)
  const [currentChapter, setCurrentChapter] = useState(0)
  const [showControls, setShowControls] = useState(true)
  const [showToc, setShowToc] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const restoredRef = useRef(false)

  const themeColors = THEME_STYLES[readerTheme]

  // Fetch book metadata for title
  const book = useQuery<BookDetail>({
    queryKey: ['book', id],
    queryFn: () => api.getBook(id!) as Promise<BookDetail>,
    enabled: !!id,
  })

  // Fetch FB2 content
  const content = useQuery<string>({
    queryKey: ['book-content', id, 'fb2'],
    queryFn: () => api.fetchBookContent(id!, 'fb2'),
    enabled: !!id,
    staleTime: Infinity,
    gcTime: 30 * 60 * 1000,
  })

  const fb2 = useMemo(() => {
    if (!content.data) return null
    try {
      return parseFB2(content.data)
    } catch (err) {
      console.error('FB2 parse error:', err)
      return null
    }
  }, [content.data])

  // Restore reading progress (runs once when fb2 loads)
  useEffect(() => {
    if (fb2 && id && !restoredRef.current) {
      restoredRef.current = true
      const saved = settings.progress[id]
      if (saved && saved.chapter < fb2.chapters.length) {
        setCurrentChapter(saved.chapter)
        // Restore scroll position after render
        if (saved.scrollPercent > 0) {
          requestAnimationFrame(() => {
            setTimeout(() => {
              const el = contentRef.current
              if (el) {
                const scrollMax = el.scrollHeight - el.clientHeight
                el.scrollTo(0, scrollMax * saved.scrollPercent)
              }
            }, 100)
          })
        }
      }
    }
  }, [fb2, id, settings])

  // Save progress on chapter/settings change (only after restore)
  useEffect(() => {
    if (id && fb2 && restoredRef.current) {
      const el = contentRef.current
      const scrollMax = el ? el.scrollHeight - el.clientHeight : 0
      const scrollPercent = el && scrollMax > 0 ? el.scrollTop / scrollMax : 0

      const s = loadSettings()
      s.progress[id] = { chapter: currentChapter, scrollPercent }
      s.fontSize = fontSize
      s.lineHeight = lineHeight
      s.fontFamily = fontFamily
      s.theme = readerTheme
      saveSettings(s)
    }
  }, [currentChapter, fontSize, lineHeight, fontFamily, readerTheme, id, fb2])

  // Save scroll position periodically
  useEffect(() => {
    const el = contentRef.current
    if (!el || !id || !fb2) return

    let saveTimer: ReturnType<typeof setTimeout>
    const handleScroll = () => {
      clearTimeout(saveTimer)
      saveTimer = setTimeout(() => {
        if (!restoredRef.current) return
        const scrollMax = el.scrollHeight - el.clientHeight
        const scrollPercent = scrollMax > 0 ? el.scrollTop / scrollMax : 0
        const s = loadSettings()
        s.progress[id] = { chapter: currentChapter, scrollPercent }
        saveSettings(s)
      }, 500)
    }

    el.addEventListener('scroll', handleScroll, { passive: true })
    return () => {
      clearTimeout(saveTimer)
      el.removeEventListener('scroll', handleScroll)
    }
  }, [id, fb2, currentChapter])

  // Scroll to top on chapter change (but not on initial restore)
  const chapterChangeRef = useRef(false)
  useEffect(() => {
    if (chapterChangeRef.current) {
      contentRef.current?.scrollTo(0, 0)
    }
    chapterChangeRef.current = true
  }, [currentChapter])

  const handleFontSize = (delta: number) => {
    setFontSize((prev) => {
      const idx = FONT_SIZES.indexOf(prev)
      const next = FONT_SIZES[Math.max(0, Math.min(FONT_SIZES.length - 1, idx + delta))]
      return next
    })
  }

  const toggleControls = () => setShowControls((v) => !v)

  // Loading state
  if (content.isLoading) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-4" style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}>
        <div className="w-10 h-10 rounded-full border-3 border-t-transparent animate-spin" style={{ borderColor: 'var(--tg-theme-button-color, #2481cc)', borderTopColor: 'transparent' }} />
        <p className="text-[15px] font-medium" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
          Загрузка книги...
        </p>
      </div>
    )
  }

  // Error state
  if (content.isError || (!content.isLoading && !fb2)) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-4 px-8" style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}>
        <div className="text-[48px] opacity-40">😔</div>
        <p className="text-[17px] font-semibold text-center" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
          Не удалось загрузить книгу
        </p>
        <p className="text-[14px] text-center" style={{ color: 'var(--tg-theme-hint-color, #999)' }}>
          Попробуйте позже или скачайте файл
        </p>
        <motion.button
          whileTap={{ scale: 0.95 }}
          onClick={goBack}
          className="mt-4 px-6 py-3 rounded-2xl text-[15px] font-semibold"
          style={{
            backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
            color: 'var(--tg-theme-button-text-color, #fff)',
          }}
        >
          Назад
        </motion.button>
      </div>
    )
  }

  if (!fb2) return null

  const chapter = fb2.chapters[currentChapter]
  const hasPrev = currentChapter > 0
  const hasNext = currentChapter < fb2.chapters.length - 1

  return (
    <div className="h-full flex flex-col" style={{ backgroundColor: themeColors.bg, transition: 'background-color 0.3s ease' }}>
      {/* Top bar */}
      <motion.div
        initial={false}
        animate={{ y: showControls ? 0 : -60, opacity: showControls ? 1 : 0 }}
        transition={{ duration: 0.2 }}
        className="flex-shrink-0 flex items-center gap-2 px-3 h-[52px] z-30"
        style={{
          backgroundColor: themeColors.bg,
          borderBottom: `0.5px solid ${readerTheme === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'}`,
          transition: 'background-color 0.3s ease',
        }}
      >
        <button onClick={goBack} className="w-10 h-10 flex items-center justify-center rounded-full" style={{ color: themeColors.accent }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>

        <div className="flex-1 min-w-0 text-center">
          <p className="text-[14px] font-semibold truncate" style={{ color: themeColors.text }}>
            {book.data?.title || fb2.title}
          </p>
          {fb2.chapters.length > 1 && (
            <p className="text-[11px]" style={{ color: `${themeColors.text}88` }}>
              {currentChapter + 1} / {fb2.chapters.length}
            </p>
          )}
        </div>

        <button
          onClick={(e) => { e.stopPropagation(); setShowSettings(true) }}
          className="w-10 h-10 flex items-center justify-center rounded-full"
          style={{ color: themeColors.accent }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
          </svg>
        </button>

        <button
          onClick={() => setShowToc(true)}
          className="w-10 h-10 flex items-center justify-center rounded-full"
          style={{ color: themeColors.accent }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
      </motion.div>

      {/* Content */}
      <div
        ref={contentRef}
        className="flex-1 overflow-y-auto overscroll-contain"
        onClick={toggleControls}
        style={{
          WebkitOverflowScrolling: 'touch',
        }}
      >
        <div
          className="fb2-content px-5 py-6 mx-auto"
          style={{
            maxWidth: '680px',
            fontSize: `${fontSize}px`,
            lineHeight: lineHeight,
            fontFamily: FONT_FAMILIES[fontFamily],
            color: themeColors.text,
            transition: 'color 0.3s ease',
          }}
        >
          {chapter.title && (
            <h1
              className="font-bold text-center mb-8"
              style={{
                fontSize: `${fontSize + 4}px`,
                color: themeColors.text,
              }}
            >
              {chapter.title}
            </h1>
          )}
          <div dangerouslySetInnerHTML={{ __html: chapter.html }} />
        </div>

        {/* Chapter navigation at bottom */}
        <div className="flex items-center justify-between px-5 py-6 max-w-[680px] mx-auto">
          {hasPrev ? (
            <motion.button
              whileTap={{ scale: 0.95 }}
              onClick={(e) => { e.stopPropagation(); setCurrentChapter((c) => c - 1) }}
              className="flex items-center gap-2 px-4 py-3 rounded-2xl text-[14px] font-semibold"
              style={{
                backgroundColor: 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
                color: 'var(--tg-theme-button-color, #2481cc)',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
              Назад
            </motion.button>
          ) : <div />}

          {hasNext ? (
            <motion.button
              whileTap={{ scale: 0.95 }}
              onClick={(e) => { e.stopPropagation(); setCurrentChapter((c) => c + 1) }}
              className="flex items-center gap-2 px-4 py-3 rounded-2xl text-[14px] font-semibold"
              style={{
                backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
                color: 'var(--tg-theme-button-text-color, #fff)',
              }}
            >
              Далее
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </motion.button>
          ) : (
            <motion.button
              whileTap={{ scale: 0.95 }}
              onClick={(e) => { e.stopPropagation(); goBack() }}
              className="flex items-center gap-2 px-4 py-3 rounded-2xl text-[14px] font-semibold"
              style={{
                backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
                color: 'var(--tg-theme-button-text-color, #fff)',
              }}
            >
              Готово
            </motion.button>
          )}
        </div>
      </div>

      {/* Bottom toolbar */}
      <motion.div
        initial={false}
        animate={{ y: showControls ? 0 : 60, opacity: showControls ? 1 : 0 }}
        transition={{ duration: 0.2 }}
        className="flex-shrink-0"
        style={{
          backgroundColor: themeColors.bg,
          borderTop: `0.5px solid ${readerTheme === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'}`,
          paddingBottom: 'var(--safe-area-bottom, 0px)',
          transition: 'background-color 0.3s ease',
        }}
      >
        {/* Progress bar */}
        {fb2.chapters.length > 1 && (
          <div className="px-5 pt-2">
            <div className="h-[3px] rounded-full overflow-hidden" style={{ backgroundColor: `${themeColors.text}15` }}>
              <div
                className="h-full rounded-full"
                style={{
                  width: `${((currentChapter + 1) / fb2.chapters.length) * 100}%`,
                  backgroundColor: themeColors.accent,
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
          </div>
        )}
        <div className="flex items-center justify-between px-5 h-[44px]">
          <span className="text-[12px] font-medium" style={{ color: `${themeColors.text}66` }}>
            {fb2.chapters.length > 1 ? `${currentChapter + 1} / ${fb2.chapters.length}` : ''}
          </span>
          <span className="text-[12px] font-medium" style={{ color: `${themeColors.text}66` }}>
            {fb2.chapters.length > 1 ? `${Math.round(((currentChapter + 1) / fb2.chapters.length) * 100)}%` : ''}
          </span>
        </div>
      </motion.div>

      {/* Settings panel */}
      {showSettings && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="fixed inset-0 z-50"
          onClick={() => setShowSettings(false)}
        >
          <div className="absolute inset-0" style={{ backgroundColor: 'rgba(0,0,0,0.4)' }} />
          <motion.div
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            transition={{ type: 'spring', damping: 28, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
            className="absolute bottom-0 left-0 right-0 rounded-t-[20px] px-5 pt-5 pb-8"
            style={{
              backgroundColor: themeColors.bg,
              paddingBottom: 'calc(var(--safe-area-bottom, 0px) + 24px)',
            }}
          >
            {/* Handle */}
            <div className="flex justify-center mb-5">
              <div className="w-9 h-1 rounded-full" style={{ backgroundColor: `${themeColors.text}20` }} />
            </div>

            {/* Font size */}
            <div className="mb-5">
              <p className="text-[12px] font-semibold uppercase tracking-wider mb-3" style={{ color: `${themeColors.text}66` }}>
                Размер шрифта
              </p>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleFontSize(-1)}
                  disabled={fontSize <= FONT_SIZES[0]}
                  className="w-10 h-10 rounded-xl flex items-center justify-center disabled:opacity-25"
                  style={{ backgroundColor: themeColors.secondary, color: themeColors.text }}
                >
                  <span className="text-[13px] font-bold">A</span>
                </button>
                <div className="flex-1 h-[6px] rounded-full overflow-hidden" style={{ backgroundColor: themeColors.secondary }}>
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${((FONT_SIZES.indexOf(fontSize)) / (FONT_SIZES.length - 1)) * 100}%`,
                      backgroundColor: themeColors.accent,
                      transition: 'width 0.2s ease',
                    }}
                  />
                </div>
                <button
                  onClick={() => handleFontSize(1)}
                  disabled={fontSize >= FONT_SIZES[FONT_SIZES.length - 1]}
                  className="w-10 h-10 rounded-xl flex items-center justify-center disabled:opacity-25"
                  style={{ backgroundColor: themeColors.secondary, color: themeColors.text }}
                >
                  <span className="text-[18px] font-bold">A</span>
                </button>
              </div>
            </div>

            {/* Line height */}
            <div className="mb-5">
              <p className="text-[12px] font-semibold uppercase tracking-wider mb-3" style={{ color: `${themeColors.text}66` }}>
                Межстрочный интервал
              </p>
              <div className="flex gap-2">
                {LINE_HEIGHTS.map((lh) => (
                  <button
                    key={lh}
                    onClick={() => setLineHeight(lh)}
                    className="flex-1 py-2.5 rounded-xl text-[13px] font-semibold transition-all"
                    style={{
                      backgroundColor: lineHeight === lh ? themeColors.accent : themeColors.secondary,
                      color: lineHeight === lh ? '#fff' : themeColors.text,
                    }}
                  >
                    {lh}
                  </button>
                ))}
              </div>
            </div>

            {/* Font family */}
            <div className="mb-5">
              <p className="text-[12px] font-semibold uppercase tracking-wider mb-3" style={{ color: `${themeColors.text}66` }}>
                Шрифт
              </p>
              <div className="flex gap-2">
                {(Object.keys(FONT_FAMILIES) as FontFamily[]).map((ff) => (
                  <button
                    key={ff}
                    onClick={() => setFontFamily(ff)}
                    className="flex-1 py-3 rounded-xl text-[14px] transition-all"
                    style={{
                      backgroundColor: fontFamily === ff ? themeColors.accent : themeColors.secondary,
                      color: fontFamily === ff ? '#fff' : themeColors.text,
                      fontFamily: FONT_FAMILIES[ff],
                      fontWeight: fontFamily === ff ? 600 : 400,
                    }}
                  >
                    {FONT_FAMILY_LABELS[ff]}
                  </button>
                ))}
              </div>
            </div>

            {/* Theme */}
            <div>
              <p className="text-[12px] font-semibold uppercase tracking-wider mb-3" style={{ color: `${themeColors.text}66` }}>
                Тема
              </p>
              <div className="flex gap-3">
                {(['light', 'sepia', 'dark'] as ReaderTheme[]).map((t) => {
                  const ts = THEME_STYLES[t]
                  const isActive = readerTheme === t
                  return (
                    <button
                      key={t}
                      onClick={() => setReaderTheme(t)}
                      className="flex-1 flex flex-col items-center gap-2 py-3 rounded-xl transition-all"
                      style={{
                        backgroundColor: ts.bg,
                        border: isActive ? `2.5px solid ${ts.accent}` : `1.5px solid ${readerTheme === 'dark' ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.1)'}`,
                      }}
                    >
                      <div className="flex gap-0.5">
                        <div className="w-3 h-4 rounded-sm" style={{ backgroundColor: ts.text, opacity: 0.7 }} />
                        <div className="w-3 h-4 rounded-sm" style={{ backgroundColor: ts.text, opacity: 0.4 }} />
                        <div className="w-3 h-4 rounded-sm" style={{ backgroundColor: ts.text, opacity: 0.2 }} />
                      </div>
                      <span className="text-[11px] font-semibold" style={{ color: ts.text }}>
                        {t === 'light' ? 'Светлая' : t === 'sepia' ? 'Сепия' : 'Тёмная'}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}

      {/* Table of Contents overlay */}
      {showToc && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex flex-col"
          style={{ backgroundColor: 'var(--tg-theme-bg-color, #fff)' }}
        >
          <div className="flex items-center gap-2 px-3 h-[52px] flex-shrink-0"
            style={{ borderBottom: '0.5px solid color-mix(in srgb, var(--tg-theme-text-color, #000) 8%, transparent)' }}
          >
            <button onClick={() => setShowToc(false)} className="w-10 h-10 flex items-center justify-center rounded-full" style={{ color: 'var(--tg-theme-button-color, #2481cc)' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
            <p className="flex-1 text-[17px] font-semibold" style={{ color: 'var(--tg-theme-text-color, #000)' }}>
              Содержание
            </p>
          </div>

          <div className="flex-1 overflow-y-auto overscroll-contain" style={{ WebkitOverflowScrolling: 'touch' }}>
            {fb2.chapters.map((ch, i) => (
              <button
                key={i}
                onClick={() => { setCurrentChapter(i); setShowToc(false) }}
                className="w-full text-left px-5 py-3.5 flex items-center gap-3 transition-colors"
                style={{
                  backgroundColor: i === currentChapter
                    ? 'color-mix(in srgb, var(--tg-theme-button-color, #2481cc) 8%, transparent)'
                    : 'transparent',
                  borderBottom: '0.5px solid color-mix(in srgb, var(--tg-theme-text-color, #000) 6%, transparent)',
                }}
              >
                <span className="text-[13px] font-bold w-7 text-center flex-shrink-0" style={{
                  color: i === currentChapter
                    ? 'var(--tg-theme-button-color, #2481cc)'
                    : 'var(--tg-theme-hint-color, #999)',
                }}>
                  {i + 1}
                </span>
                <span className="text-[15px] flex-1 truncate" style={{
                  color: i === currentChapter
                    ? 'var(--tg-theme-button-color, #2481cc)'
                    : 'var(--tg-theme-text-color, #000)',
                  fontWeight: i === currentChapter ? 600 : 400,
                }}>
                  {ch.title}
                </span>
                {i === currentChapter && (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--tg-theme-button-color, #2481cc)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </button>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  )
}
