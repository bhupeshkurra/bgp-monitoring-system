import { createContext, useContext, useEffect, useState } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'

const WebSocketContext = createContext(null)

export function WebSocketProvider({ children }) {
  const [anomalies, setAnomalies] = useState([])
  const [stats, setStats] = useState(null)
  const [notifications, setNotifications] = useState([])
  
  // Dashboard widget data from WebSocket
  const [churnData, setChurnData] = useState(null)
  const [flapsData, setFlapsData] = useState(null)
  const [volumeData, setVolumeData] = useState(null)
  const [rpkiData, setRpkiData] = useState(null)
  
  // Connect directly to backend WebSocket server on port 5000
  const { isConnected, on, off, emit } = useWebSocket('http://localhost:5000', {
    transports: ['polling', 'websocket']
  })

  useEffect(() => {
    if (!isConnected) return

    // Subscribe to new anomalies
    const handleNewAnomaly = (anomaly) => {
      console.log('[WebSocket] New anomaly received:', anomaly)
      
      // Add to anomalies list (keep last 100)
      setAnomalies(prev => [anomaly, ...prev].slice(0, 100))
      
      // Create notification for critical/high severity
      if (anomaly.severity === 'critical' || anomaly.severity === 'high') {
        const notification = {
          id: Date.now(),
          title: `${anomaly.severity.toUpperCase()}: ${anomaly.type}`,
          message: `Prefix: ${anomaly.prefix} - ${anomaly.classification}`,
          severity: anomaly.severity,
          timestamp: anomaly.timestamp
        }
        setNotifications(prev => [notification, ...prev].slice(0, 50))
      }
    }

    // Subscribe to stats updates
    const handleStats = (statsData) => {
      console.log('[WebSocket] Stats update:', statsData)
      setStats(statsData)
    }

    // Subscribe to consolidated dashboard updates
    const handleDashboardUpdate = (data) => {
      console.log('[WebSocket] Dashboard update received')
      
      if (data.churn) setChurnData(data.churn)
      if (data.flaps) setFlapsData(data.flaps)
      if (data.volume) setVolumeData(data.volume)
      if (data.rpki) setRpkiData(data.rpki)
    }

    // Register event listeners
    on('new_anomaly', handleNewAnomaly)
    on('anomaly_stats', handleStats)
    on('dashboard_update', handleDashboardUpdate)

    // Request subscription
    emit('subscribe', { feed: 'anomalies' })

    // Cleanup
    return () => {
      off('new_anomaly', handleNewAnomaly)
      off('anomaly_stats', handleStats)
      off('dashboard_update', handleDashboardUpdate)
    }
  }, [isConnected, on, off, emit])

  const value = {
    isConnected,
    anomalies,
    stats,
    notifications,
    clearNotifications: () => setNotifications([]),
    // Dashboard widget data consolidated
    dashboardData: {
      churn: churnData,
      flaps: flapsData,
      volume: volumeData,
      rpki: rpkiData
    }
  }

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  )
}

export function useWebSocketContext() {
  const context = useContext(WebSocketContext)
  if (!context) {
    throw new Error('useWebSocketContext must be used within WebSocketProvider')
  }
  return context
}
