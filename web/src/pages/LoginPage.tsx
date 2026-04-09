/**
 * LoginPage — mirrors time_jedi_bot/web/frontend/src/pages/LoginPage.tsx
 *
 * Two auth paths:
 * 1. Inside Telegram Mini App → auto-login via initData
 * 2. Browser → Telegram Login Widget
 */

import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../store/auth'
import { loginWithInitData, loginWithWidget } from '../api/client'
import type { AuthUser } from '../store/auth'

const BOT_USERNAME = 'flibusta_rebot'

interface TelegramAuthData {
  id: number
  first_name: string
  last_name?: string
  username?: string
  photo_url?: string
  auth_date: number
  hash: string
}

function StarField() {
  const stars = useMemo(
    () =>
      Array.from({ length: 50 }, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        y: Math.random() * 100,
        size: Math.random() * 2 + 0.5,
        delay: Math.random() * 4,
        duration: Math.random() * 3 + 2,
      })),
    []
  )

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {stars.map((star) => (
        <div
          key={star.id}
          className="absolute rounded-full"
          style={{
            left: `${star.x}%`,
            top: `${star.y}%`,
            width: `${star.size}px`,
            height: `${star.size}px`,
            backgroundColor: 'rgba(255,255,255,0.4)',
            animation: `twinkle ${star.duration}s ${star.delay}s ease-in-out infinite`,
          }}
        />
      ))}
    </div>
  )
}

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const postLoginPath = useCallback(() => {
    const from = (location.state as { from?: string } | null)?.from
    if (from && from !== '/login') return from
    return '/'
  }, [location.state])

  const containerRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [autoAuthTried, setAutoAuthTried] = useState(false)
  const [widgetLoading, setWidgetLoading] = useState(false)
  const [widgetFailed, setWidgetFailed] = useState(false)
  const [widgetReloadKey, setWidgetReloadKey] = useState(0)

  // 1. Auto-login via Telegram Mini App initData
  useEffect(() => {
    if (autoAuthTried) return
    setAutoAuthTried(true)

    const initData = window.Telegram?.WebApp?.initData
    if (!initData) return

    setLoading(true)
    setError(null)
    loginWithInitData(initData)
      .then(({ access_token, user }) => {
        login(access_token, user as unknown as AuthUser)
        navigate(postLoginPath(), { replace: true })
      })
      .catch((err: unknown) => {
        setError((err as Error).message || 'Не удалось авторизоваться через Telegram Mini App.')
      })
      .finally(() => setLoading(false))
  }, [autoAuthTried, login, navigate, postLoginPath])

  // 2. Telegram Login Widget (browser fallback)
  useEffect(() => {
    ;(window as unknown as Record<string, unknown>).onTelegramAuth = async (userData: TelegramAuthData) => {
      setError(null)
      setLoading(true)
      try {
        const { access_token, user } = await loginWithWidget(userData as unknown as Record<string, unknown>)
        login(access_token, user as unknown as AuthUser)
        navigate(postLoginPath(), { replace: true })
      } catch (err: unknown) {
        setError((err as Error).message || 'Ошибка авторизации.')
      } finally {
        setLoading(false)
      }
    }

    if (!containerRef.current) return

    const hasWebAppInitData = Boolean(window.Telegram?.WebApp?.initData)
    if (hasWebAppInitData) {
      containerRef.current.innerHTML = ''
      return
    }

    setWidgetLoading(true)
    setWidgetFailed(false)
    containerRef.current.innerHTML = ''

    const script = document.createElement('script')
    script.src = 'https://telegram.org/js/telegram-widget.js?22'
    script.setAttribute('data-telegram-login', BOT_USERNAME)
    script.setAttribute('data-size', 'large')
    script.setAttribute('data-onauth', 'onTelegramAuth(user)')
    script.setAttribute('data-request-access', 'write')
    script.onerror = () => { setWidgetFailed(true); setWidgetLoading(false) }
    script.onload = () => {
      window.setTimeout(() => {
        const hasWidget = Boolean(containerRef.current?.childElementCount)
        setWidgetLoading(false)
        if (!hasWidget) setWidgetFailed(true)
      }, 1300)
    }
    script.async = true
    containerRef.current.appendChild(script)

    const timeoutId = window.setTimeout(() => {
      if (!containerRef.current?.childElementCount) setWidgetFailed(true)
      setWidgetLoading(false)
    }, 6000)

    return () => {
      delete (window as unknown as Record<string, unknown>).onTelegramAuth
      window.clearTimeout(timeoutId)
    }
  }, [login, navigate, postLoginPath, widgetReloadKey])

  return (
    <div className="h-full flex items-center justify-center relative overflow-hidden"
      style={{ background: 'linear-gradient(160deg, #0a0e27 0%, #1a1040 40%, #0d1b2a 100%)' }}>
      <StarField />

      <div className="absolute top-1/4 -left-32 w-80 h-80 rounded-full opacity-30 blur-[80px] pointer-events-none"
        style={{ background: 'radial-gradient(circle, #6366f1, transparent)' }} />
      <div className="absolute bottom-1/4 -right-32 w-80 h-80 rounded-full opacity-20 blur-[80px] pointer-events-none"
        style={{ background: 'radial-gradient(circle, #06b6d4, transparent)' }} />

      <div className="relative z-10 w-full max-w-sm mx-4">
        <div className="rounded-2xl p-px"
          style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.4), rgba(6,182,212,0.2), rgba(99,102,241,0.1))' }}>
          <div className="rounded-2xl p-8"
            style={{
              background: 'rgba(15, 12, 41, 0.85)',
              backdropFilter: 'blur(40px) saturate(150%)',
              boxShadow: '0 0 60px rgba(99,102,241,0.15)',
            }}>

            {/* Icon */}
            <div className="flex justify-center mb-5">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center"
                style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)', boxShadow: '0 0 30px rgba(99,102,241,0.4)' }}>
                <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
                  <path d="M8 7h8M8 11h6" />
                </svg>
              </div>
            </div>

            <h1 className="text-2xl font-bold text-white text-center">Flibusta</h1>
            <p className="text-indigo-300/70 text-sm font-medium text-center mt-1.5 tracking-wide">
              Книги и аудиокниги
            </p>

            <ul className="space-y-3 mt-6 mb-6">
              {[
                { icon: '🔍', text: 'Поиск книг по названию и автору' },
                { icon: '🎧', text: 'Аудиокниги с онлайн-прослушиванием' },
                { icon: '📚', text: 'Личная библиотека и история' },
                { icon: '📥', text: 'Скачивание в fb2, epub, pdf' },
              ].map(({ icon, text }) => (
                <li key={text} className="flex items-center gap-3 text-sm text-violet-100/70">
                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl text-lg"
                    style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.15)' }}>
                    {icon}
                  </span>
                  <span>{text}</span>
                </li>
              ))}
            </ul>

            <div className="relative py-1 mb-5">
              <div className="absolute inset-x-0 top-1/2 border-t border-indigo-300/15" />
              <div className="relative flex justify-center">
                <span className="px-3 text-xs text-violet-100/40"
                  style={{ backgroundColor: 'rgba(15, 12, 41, 0.85)' }}>
                  Войдите через Telegram
                </span>
              </div>
            </div>

            <div ref={containerRef} className="flex justify-center min-h-[44px]" />

            {widgetLoading && (
              <p className="text-xs text-violet-100/50 text-center mt-3 animate-pulse">
                Загружаем Telegram Login Widget...
              </p>
            )}

            {widgetFailed && (
              <div className="mt-3 p-3 rounded-xl" style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)' }}>
                <p className="text-xs text-amber-200/80 text-center">
                  Виджет не загрузился. Попробуйте ещё раз или откройте через бота.
                </p>
                <div className="mt-2 flex items-center justify-center gap-2">
                  <button onClick={() => setWidgetReloadKey(k => k + 1)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium text-violet-200/80"
                    style={{ background: 'rgba(99,102,241,0.15)' }}>
                    Повторить
                  </button>
                  <a href={`https://t.me/${BOT_USERNAME}`} target="_blank" rel="noreferrer"
                    className="px-3 py-1.5 rounded-lg text-xs font-medium text-white"
                    style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)' }}>
                    Открыть бота
                  </a>
                </div>
              </div>
            )}

            {loading && (
              <p className="text-xs text-indigo-300 text-center mt-3 animate-pulse">Выполняется вход...</p>
            )}

            {error && (
              <div className="mt-3 p-3 rounded-xl" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
                <p className="text-xs text-red-300 text-center">{error}</p>
              </div>
            )}
          </div>
        </div>

        <p className="text-center text-xs text-violet-100/25 mt-5 px-4">
          Авторизация через официальный Telegram Login Widget.
          <br />Мы не храним пароли и не публикуем записи.
        </p>
      </div>
    </div>
  )
}
