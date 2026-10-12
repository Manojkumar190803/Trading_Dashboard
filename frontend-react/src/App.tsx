import './styles/globals.css'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useAppStore } from '@/stores'
import { ToastProvider } from '@/components/Toast'
import Layout from '@/components/Layout'
import Dashboard from '@/pages/Dashboard'
import Positions from '@/pages/Positions'
import Orderbook from '@/pages/Orderbook'
import Analytics from '@/pages/Analytics'
import Logs from '@/pages/Logs'
import Instruments from '@/pages/Instruments'

function App() {
  const [isReady, setIsReady] = useState(false)
  const { setTheme } = useAppStore()

  useEffect(() => {
    // Initialize theme from localStorage
    const savedTheme = localStorage.getItem('theme') as 'dark' | 'light' | null
    const preferredTheme = savedTheme || 'dark'
    setTheme(preferredTheme)
    setIsReady(true)
  }, [setTheme])

  if (!isReady) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-bg-primary">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-accent-cyan border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-text-secondary">Initializing dashboard...</p>
        </div>
      </div>
    )
  }

  return (
    <ToastProvider>
      <Router>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/positions" element={<Positions />} />
            <Route path="/orderbook" element={<Orderbook />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/instruments" element={<Instruments />} />
            <Route path="/logs" element={<Logs />} />
          </Routes>
        </Layout>
      </Router>
    </ToastProvider>
  )
}

export default App
