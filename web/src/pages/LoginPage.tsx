import { useState, useEffect, useRef, useMemo } from 'react'
import { loginWithInitData, storeAuth } from '../api/client'

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

interface LoginPageProps {
  onLogin: (token: string, user: Record<string, unknown>) => void
  autoLoginError?: string | null
}

export default function LoginPage({ onLogin, autoLoginError }: LoginPageProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(autoLoginError || null)
  const [loading, setLoading] = useState(false)
  const [widgetLoading, setWidgetLoading] = useState(false)
  const [widgetFailed, setWidgetFailed] = useState(false)
  const [widgetReloadKey, setWidgetReloadKey] = useState(0)

  // Try auto-login with initData (inside Telegram)
  useEffect(() => {
    const initData = window.Telegram?.WebApp?.initData
    if (!initData) return

    setLoading(true)
    loginWithInitData(initData)
      .then(({ access_token, user }) => {
        storeAuth(access_token, user)
        onLogin(access_token, user)
      })
      .catch((err) => {
        setError(err.message || 'Не удалось авторизоваться через Telegram Mini App.')
        setLoading(false)
      })
  }, [onLogin])

  // Load Telegram Login Widget (outside Telegram)
  useEffect(() => {
    ;(window as unknown as Record<string, unknown>).onTelegramAuth = async (userData: TelegramAuthData) => {
      setError(null)
      setLoading(true)
      try {
        // Send widget data to our backend
        const res = await fetch('/api/auth/telegram-widget', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(userData),
        })
        if (!res.ok) throw new Error(`Auth failed: ${res.status}`)
        const data = await res.json()
        storeAuth(data.access_token, data.user)
        onLogin(data.access_token, data.user)
      } catch (err: unknown) {
        const msg = (err as Error).message || 'Ошибка авторизации'
        setError(msg)
      } finally {
        setLoading(false)
      }
    }

    if (!containerRef.current) return

    const hasWebAppInitData = Boolean(window.Telegram?.WebApp?.initData)
    if (hasWebAppInitData) {
      setWidgetLoading(false)
      setWidgetFailed(false)
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
    script.onerror = () => {
      setWidgetFailed(true)
      setWidgetLoading(false)
    }
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
  }, [onLogin, widgetReloadKey])

  return (
    <div className="h-full flex items-center justify-center relative overflow-hidden"
      style={{ background: 'linear-gradient(160deg, #0a0e27 0%, #1a1040 40%, #0d1b2a 100%)' }}>
      <StarField />

      {/* Gradient orbs */}
      <div className="absolute top-1/4 -left-32 w-80 h-80 rounded-full opacity-30 blur-[80px] pointer-events-none"
        style={{ background: 'radial-gradient(circle, #6366f1, transparent)' }} />
      <div className="absolute bottom-1/4 -right-32 w-80 h-80 rounded-full opacity-20 blur-[80px] pointer-events-none"
        style={{ background: 'radial-gradient(circle, #06b6d4, transparent)' }} />

      <div className="relative z-10 w-full max-w-sm mx-4">
        {/* Card */}
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
                style={{
                  background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
                  boxShadow: '0 0 30px rgba(99,102,241,0.4)',
                }}>
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

            {/* Features */}
            <ul className="space-y-3 mt-6 mb-6">
              {[
                { icon: '🔍', text: 'Поиск книг по названию и автору' },
                { icon: '🎧', text: 'Аудиокниги с онлайн-прослушиванием' },
                { icon: '📚', text: 'Личная библиотека и история' },
                { icon: '📥', text: 'Скачивание в fb2, epub, pdf' },
              ].map(({ icon, text }) => (
                <li key={text} className="flex items-center gap-3 text-sm text-violet-100/70">
                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl text-lg"
                    style={{
                      background: 'rgba(99,102,241,0.1)',
                      border: '1px solid rgba(99,102,241,0.15)',
                    }}>
                    {icon}
                  </span>
                  <span>{text}</span>
                </li>
              ))}
            </ul>

            {/* Divider */}
            <div className="relative py-1 mb-5">
              <div className="absolute inset-x-0 top-1/2 border-t border-indigo-300/15" />
              <div className="relative flex justify-center">
                <span className="px-3 text-xs text-violet-100/40"
                  style={{ backgroundColor: 'rgba(15, 12, 41, 0.85)' }}>
                  Войдите через Telegram
                </span>
              </div>
            </div>

            {/* Telegram Widget container */}
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
                  <button
                    onClick={() => setWidgetReloadKey(k => k + 1)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium text-violet-200/80 hover:text-white transition-colors"
                    style={{ background: 'rgba(99,102,241,0.15)' }}>
                    Повторить
                  </button>
                  <a
                    href={`https://t.me/${BOT_USERNAME}`}
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-1.5 rounded-lg text-xs font-medium text-white"
                    style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)' }}>
                    Открыть бота
                  </a>
                </div>
              </div>
            )}

            {loading && (
              <p className="text-xs text-indigo-300 text-center mt-3 animate-pulse">
                Выполняется вход...
              </p>
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
          <br />
          Мы не храним пароли и не публикуем записи.
        </p>
      </div>
    </div>
  )
}
