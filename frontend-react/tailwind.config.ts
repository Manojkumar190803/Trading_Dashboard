import type { Config } from 'tailwindcss'
import defaultTheme from 'tailwindcss/defaultTheme'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: {
          primary: 'rgb(var(--bg-primary-rgb) / <alpha-value>)',
          secondary: 'rgb(var(--bg-secondary-rgb) / <alpha-value>)',
          tertiary: 'rgb(var(--bg-tertiary-rgb) / <alpha-value>)',
          surface: 'rgb(var(--bg-surface-rgb) / <alpha-value>)',
        },
        text: {
          primary: 'rgb(var(--text-primary-rgb) / <alpha-value>)',
          secondary: 'rgb(var(--text-secondary-rgb) / <alpha-value>)',
          tertiary: 'rgb(var(--text-tertiary-rgb) / <alpha-value>)',
        },
        accent: {
          cyan: 'rgb(var(--accent-cyan-rgb) / <alpha-value>)',
          green: 'rgb(var(--accent-green-rgb) / <alpha-value>)',
          red: 'rgb(var(--accent-red-rgb) / <alpha-value>)',
          yellow: 'rgb(var(--accent-yellow-rgb) / <alpha-value>)',
          blue: 'rgb(var(--accent-blue-rgb) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['Inter', ...defaultTheme.fontFamily.sans],
        mono: ['JetBrains Mono', ...defaultTheme.fontFamily.mono],
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1rem' }],
        sm: ['0.875rem', { lineHeight: '1.25rem' }],
        base: ['1rem', { lineHeight: '1.5rem' }],
        lg: ['1.125rem', { lineHeight: '1.75rem' }],
        xl: ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem' }],
      },
      boxShadow: {
        glow: '0 0 20px rgba(89, 208, 255, 0.15)',
        'glow-green': '0 0 20px rgba(39, 212, 138, 0.15)',
        'glow-red': '0 0 20px rgba(255, 95, 109, 0.15)',
        card: '0 4px 6px rgba(0, 0, 0, 0.1), 0 1px 3px rgba(0, 0, 0, 0.08)',
        'card-hover': '0 20px 25px -5px rgba(0, 0, 0, 0.3)',
        'light-card': '0 1px 3px rgba(0, 0, 0, 0.08), 0 2px 8px rgba(0, 0, 0, 0.05)',
        'light-card-hover': '0 4px 12px rgba(0, 0, 0, 0.12), 0 2px 6px rgba(0, 0, 0, 0.08)',
      },
      backdropBlur: {
        xs: '2px',
      },
      animation: {
        'pulse-soft': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-in': 'slideIn 0.4s ease-out',
        'bounce-soft': 'bounceSoft 1s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          'from': { opacity: '0' },
          'to': { opacity: '1' },
        },
        slideIn: {
          'from': { transform: 'translateY(10px)', opacity: '0' },
          'to': { transform: 'translateY(0)', opacity: '1' },
        },
        bounceSoft: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-4px)' },
        },
      },
      borderRadius: {
        xl: '1rem',
        '2xl': '1.5rem',
        '3xl': '2rem',
      },
      opacity: {
        4: '0.04',
        8: '0.08',
        12: '0.12',
      },
    },
  },
  plugins: [
    function ({ addBase, addVariant, theme }: any) {
      addVariant('light', 'html.light &')
      addBase({
        'body': {
          color: theme('colors.text.primary'),
          backgroundColor: theme('colors.bg.primary'),
        },
        'h1, h2, h3, h4, h5, h6': {
          color: theme('colors.text.primary'),
        },
      })
    },
  ],
} satisfies Config
