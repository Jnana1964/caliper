/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 900: '#07070b', 800: '#0c0d13', 700: '#13141c', 600: '#1b1d27', 500: '#262936' },
        line: '#262936',
        mist: { 100: '#f2f3f7', 300: '#b9bdcc', 500: '#7c8198' },
        acc: { DEFAULT: '#5eead4', deep: '#14b8a6', glow: 'rgba(94,234,212,0.14)' },
        warn: '#fbbf24',
        bad: '#fb7185',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      keyframes: {
        rise: { '0%': { opacity: 0, transform: 'translateY(8px)' }, '100%': { opacity: 1, transform: 'none' } },
        pulseRing: { '0%,100%': { boxShadow: '0 0 0 0 rgba(94,234,212,0.35)' }, '50%': { boxShadow: '0 0 0 6px rgba(94,234,212,0)' } },
      },
      animation: { rise: 'rise .35s ease both', ring: 'pulseRing 1.6s ease-in-out infinite' },
    },
  },
  plugins: [],
}
