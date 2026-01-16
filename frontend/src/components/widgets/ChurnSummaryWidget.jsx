import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useWebSocketContext } from '../../contexts/WebSocketContext'

function ChurnSummaryWidget({ timeRange, filters }) {
  const { dashboardData, isConnected } = useWebSocketContext()
  const [loading, setLoading] = useState(true)

  const displayData = dashboardData?.churn || null

  useEffect(() => {
    if (displayData) {
      setLoading(false)
    }
  }, [displayData])

  if (loading && !displayData) return <div className="widget"><div className="loading">Loading churn data...</div></div>
  if (!displayData) return <div className="widget"><div className="loading">No data</div></div>

  return (
    <div className="widget">
      <div className="widget-header">
        <div>
          <h3 className="widget-title">
            Churn Summary
            {isConnected && <span style={{ marginLeft: '0.5rem', fontSize: '0.7rem', color: '#3fb950' }}>● LIVE</span>}
          </h3>
          <p className="widget-subtitle">Announcements vs Withdrawals</p>
        </div>
      </div>
      <div className="widget-body">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={displayData.timeSeries}>
            <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
            <XAxis dataKey="time" stroke="#8b949e" />
            <YAxis stroke="#8b949e" />
            <Tooltip 
              contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
              labelStyle={{ color: '#e1e4e8' }}
            />
            <Legend />
            <Line type="monotone" dataKey="announcements" stroke="#3fb950" strokeWidth={2} />
            <Line type="monotone" dataKey="withdrawals" stroke="#f85149" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>

        {displayData.topPrefixes && (
          <div style={{ marginTop: '1.5rem' }}>
            <h4 style={{ fontSize: '0.9rem', marginBottom: '0.75rem', color: '#8b949e' }}>
              Top Churning Prefixes
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {displayData.topPrefixes.slice(0, 5).map((item, idx) => (
                <div key={idx} style={{ 
                  display: 'flex', 
                  justifyContent: 'space-between',
                  padding: '0.5rem',
                  background: '#1a1f2e',
                  borderRadius: '4px',
                  fontSize: '0.85rem'
                }}>
                  <span>{item.prefix}</span>
                  <span style={{ color: getSeverityColor(item.severity) }}>
                    {item.count} updates
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function getSeverityColor(severity) {
  const colors = {
    critical: '#f85149',
    high: '#db6d28',
    medium: '#d29922',
    low: '#3fb950'
  }
  return colors[severity] || '#8b949e'
}

export default ChurnSummaryWidget
