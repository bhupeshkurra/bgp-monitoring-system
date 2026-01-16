import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { useWebSocketContext } from '../../contexts/WebSocketContext'

function RouteFlapWidget({ timeRange, filters }) {
  const { dashboardData, isConnected } = useWebSocketContext()
  const [loading, setLoading] = useState(true)

  const displayData = dashboardData?.flaps || null

  useEffect(() => {
    if (displayData) {
      setLoading(false)
    }
  }, [displayData])

  if (loading && !displayData) return <div className="widget"><div className="loading">Loading flap data...</div></div>
  if (!displayData) return <div className="widget"><div className="loading">No data</div></div>

  const threshold = displayData.threshold || 10

  return (
    <div className="widget">
      <div className="widget-header">
        <div>
          <h3 className="widget-title">
            Route Flap Rate
            {isConnected && <span style={{ marginLeft: '0.5rem', fontSize: '0.7rem', color: '#3fb950' }}>● LIVE</span>}
          </h3>
          <p className="widget-subtitle">Threshold: {threshold} flaps/hour</p>
        </div>
        {displayData.alerts?.length > 0 && (
          <div style={{ 
            background: 'rgba(248, 81, 73, 0.2)',
            color: '#f85149',
            padding: '0.5rem 1rem',
            borderRadius: '4px',
            fontSize: '0.85rem',
            fontWeight: '600'
          }}>
            {displayData.alerts.length} Alert{displayData.alerts.length > 1 ? 's' : ''}
          </div>
        )}
      </div>
      <div className="widget-body">
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={displayData.timeSeries}>
            <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
            <XAxis dataKey="time" stroke="#8b949e" />
            <YAxis stroke="#8b949e" />
            <Tooltip 
              contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
              labelStyle={{ color: '#e1e4e8' }}
            />
            <ReferenceLine y={threshold} stroke="#f85149" strokeDasharray="5 5" label="Threshold" />
            <Line type="monotone" dataKey="flaps" stroke="#58a6ff" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>

        {displayData.alerts?.length > 0 && (
          <div style={{ marginTop: '1rem', marginBottom: '1rem' }}>
            {displayData.alerts.slice(0, 3).map((alert, idx) => (
              <div key={idx} style={{
                background: 'rgba(248, 81, 73, 0.1)',
                border: '1px solid rgba(248, 81, 73, 0.3)',
                borderRadius: '4px',
                padding: '0.75rem',
                marginBottom: '0.5rem',
                fontSize: '0.85rem'
              }}>
                {alert.message}
              </div>
            ))}
          </div>
        )}

        {displayData.peers && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: '0.85rem', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #30363d', color: '#8b949e' }}>
                  <th style={{ padding: '0.5rem', textAlign: 'left' }}>Prefix/Peer</th>
                  <th style={{ padding: '0.5rem', textAlign: 'center' }}>Flap Count</th>
                  <th style={{ padding: '0.5rem', textAlign: 'center' }}>Rate</th>
                  <th style={{ padding: '0.5rem', textAlign: 'center' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {displayData.peers.slice(0, 5).map((peer, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid #30363d' }}>
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>{peer.prefix}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'center' }}>{peer.flapCount}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'center' }}>{peer.rate}/hr</td>
                    <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                      <span style={{
                        padding: '0.25rem 0.5rem',
                        borderRadius: '4px',
                        background: getStatusBg(peer.status),
                        color: getStatusColor(peer.status),
                        fontSize: '0.75rem',
                        fontWeight: '600'
                      }}>
                        {peer.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function getStatusColor(status) {
  const colors = {
    stable: '#3fb950',
    unstable: '#d29922',
    critical: '#f85149'
  }
  return colors[status] || '#8b949e'
}

function getStatusBg(status) {
  const colors = {
    stable: 'rgba(63, 185, 80, 0.2)',
    unstable: 'rgba(210, 153, 34, 0.2)',
    critical: 'rgba(248, 81, 73, 0.2)'
  }
  return colors[status] || 'rgba(139, 148, 158, 0.2)'
}

export default RouteFlapWidget
