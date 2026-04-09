import { useEffect, useCallback } from 'react'

declare global {
  interface Window {
    Telegram?: {
      WebApp: {
        ready: () => void
        expand: () => void
        close: () => void
        initData: string
        initDataUnsafe: {
          user?: {
            id: number
            first_name: string
            last_name?: string
            username?: string
            photo_url?: string
          }
        }
        themeParams: Record<string, string>
        colorScheme: 'light' | 'dark'
        BackButton: {
          show: () => void
          hide: () => void
          onClick: (cb: () => void) => void
          offClick: (cb: () => void) => void
          isVisible: boolean
        }
        MainButton: {
          show: () => void
          hide: () => void
          setText: (text: string) => void
          onClick: (cb: () => void) => void
          offClick: (cb: () => void) => void
          showProgress: (leaveActive?: boolean) => void
          hideProgress: () => void
          setParams: (params: { color?: string; text_color?: string; is_active?: boolean; is_visible?: boolean }) => void
        }
        HapticFeedback: {
          impactOccurred: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void
          notificationOccurred: (type: 'error' | 'success' | 'warning') => void
          selectionChanged: () => void
        }
        isVersionAtLeast: (version: string) => boolean
        platform: string
      }
    }
  }
}

export function useTelegram() {
  const tg = window.Telegram?.WebApp

  useEffect(() => {
    if (tg) {
      tg.ready()
      tg.expand()
    }
  }, [tg])

  return tg
}

export function useBackButton(onBack: (() => void) | null) {
  const tg = window.Telegram?.WebApp

  useEffect(() => {
    if (!tg) return

    if (onBack) {
      tg.BackButton.show()
      tg.BackButton.onClick(onBack)
      return () => {
        tg.BackButton.offClick(onBack)
        tg.BackButton.hide()
      }
    } else {
      tg.BackButton.hide()
    }
  }, [tg, onBack])
}

export function useHaptic() {
  const tg = window.Telegram?.WebApp

  const impact = useCallback(
    (style: 'light' | 'medium' | 'heavy' = 'light') => {
      tg?.HapticFeedback?.impactOccurred(style)
    },
    [tg]
  )

  const notification = useCallback(
    (type: 'success' | 'error' | 'warning') => {
      tg?.HapticFeedback?.notificationOccurred(type)
    },
    [tg]
  )

  const selection = useCallback(() => {
    tg?.HapticFeedback?.selectionChanged()
  }, [tg])

  return { impact, notification, selection }
}

export function getTelegramUser() {
  return window.Telegram?.WebApp?.initDataUnsafe?.user
}
