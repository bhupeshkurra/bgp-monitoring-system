import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { WebSocketProvider } from './contexts/WebSocketContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import PrefixForensics from './pages/PrefixForensics'
import AdvancedAnalytics from './pages/AdvancedAnalytics'
import HistoricalPlayback from './pages/HistoricalPlayback'

function App() {
  return (
    <WebSocketProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="prefix-forensics" element={<PrefixForensics />} />
            <Route path="advanced-analytics" element={<AdvancedAnalytics />} />
            <Route path="historical-playback" element={<HistoricalPlayback />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </WebSocketProvider>
  )
}

export default App
