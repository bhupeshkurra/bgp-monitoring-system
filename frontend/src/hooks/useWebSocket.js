import { useEffect, useState, useRef, useCallback } from 'react'
import { io } from 'socket.io-client'

/**
 * WebSocket hook for real-time BGP anomaly updates
 * Connects to backend Socket.IO server for live data streaming
 */
export function useWebSocket(url, options = {}) {
  const [isConnected, setIsConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState(null)
  const [error, setError] = useState(null)
  const socketRef = useRef(null)
  const listenersRef = useRef({})

  useEffect(() => {
    if (!url) return

    // Create Socket.IO connection
    const socket = io(url, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5,
      ...options
    })

    socketRef.current = socket

    // Connection events
    socket.on('connect', () => {
      console.log('[WebSocket] Connected to server')
      setIsConnected(true)
      setError(null)
    })

    socket.on('disconnect', (reason) => {
      console.log('[WebSocket] Disconnected:', reason)
      setIsConnected(false)
    })

    socket.on('connect_error', (err) => {
      console.error('[WebSocket] Connection error:', err.message)
      setError(err.message)
    })

    socket.on('connection_established', (data) => {
      console.log('[WebSocket] Connection established:', data)
    })

    // Cleanup
    return () => {
      if (socket) {
        console.log('[WebSocket] Disconnecting...')
        socket.disconnect()
      }
    }
  }, [url])

  // Subscribe to events
  const on = useCallback((event, handler) => {
    if (!socketRef.current) return

    // Store handler reference
    listenersRef.current[event] = handler

    // Register with Socket.IO
    socketRef.current.on(event, handler)
  }, [])

  // Unsubscribe from events
  const off = useCallback((event, handler) => {
    if (!socketRef.current) return

    socketRef.current.off(event, handler)
    
    if (listenersRef.current[event]) {
      delete listenersRef.current[event]
    }
  }, [])

  // Emit events to server
  const emit = useCallback((event, data) => {
    if (!socketRef.current || !isConnected) {
      console.warn('[WebSocket] Cannot emit - not connected')
      return
    }

    socketRef.current.emit(event, data)
  }, [isConnected])

  return {
    isConnected,
    lastMessage,
    error,
    on,
    off,
    emit,
    socket: socketRef.current
  }
}
