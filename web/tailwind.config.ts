import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        tg: {
          bg: 'var(--tg-theme-bg-color, #ffffff)',
          text: 'var(--tg-theme-text-color, #000000)',
          hint: 'var(--tg-theme-hint-color, #999999)',
          link: 'var(--tg-theme-link-color, #2481cc)',
          button: 'var(--tg-theme-button-color, #2481cc)',
          'button-text': 'var(--tg-theme-button-text-color, #ffffff)',
          'secondary-bg': 'var(--tg-theme-secondary-bg-color, #f0f0f0)',
          'header-bg': 'var(--tg-theme-header-bg-color, #ffffff)',
          'section-bg': 'var(--tg-theme-section-bg-color, #ffffff)',
          'section-header': 'var(--tg-theme-section-header-text-color, #6d6d72)',
          subtitle: 'var(--tg-theme-subtitle-text-color, #6d6d72)',
          destructive: 'var(--tg-theme-destructive-text-color, #ff3b30)',
        },
      },
      fontFamily: {
        sans: [
          '-apple-system', 'BlinkMacSystemFont', 'SF Pro Text', 'SF Pro Display',
          'Helvetica Neue', 'Helvetica', 'Arial', 'sans-serif',
        ],
      },
      borderRadius: {
        'ios': '12px',
        'ios-lg': '16px',
        'ios-xl': '20px',
      },
      boxShadow: {
        'float': '0 4px 16px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.04)',
        'float-lg': '0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)',
        'inner-glow': 'inset 0 1px 0 rgba(255,255,255,0.06)',
      },
      animation: {
        'skeleton': 'skeleton 1.5s ease-in-out infinite',
      },
      keyframes: {
        skeleton: {
          '0%': { opacity: '0.4' },
          '50%': { opacity: '0.7' },
          '100%': { opacity: '0.4' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config
