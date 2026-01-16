import { useState, useEffect } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts'
import { useWebSocketContext } from '../../contexts/WebSocketContext'

function RpkiSummaryWidget({ timeRange, filters }) {
  const { dashboardData, isConnected } = useWebSocketContext()
  const [loading, setLoading] = useState(true)

  const displayData = dashboardData?.rpki || null

  useEffect(() => {
    if (displayData) {
      setLoading(false)
    }
  }, [displayData])

  if (loading && !displayData) return <div className="widget"><div className="loading">Loading RPKI data...</div></div>
  if (!displayData || !displayData.summary) return <div className="widget"><div className="loading">No data</div></div>

  const chartData = [
    { name: 'Valid', value: displayData.summary.valid || 0, color: '#3fb950' },
    { name: 'Invalid', value: displayData.summary.invalid || 0, color: '#f85149' },
    { name: 'Unknown', value: displayData.summary.unknown || 0, color: '#d29922' }
  ]

  const total = chartData.reduce((sum, item) => sum + item.value, 0)

  return (
    <div className="widget">
      <div className="widget-header">
        <div>
          <h3 className="widget-title">
            RPKI Validation Summary
            {isConnected && <span style={{ marginLeft: '0.5rem', fontSize: '0.7rem', color: '#3fb950' }}>● LIVE</span>}
          </h3>
          <p className="widget-subtitle">Total: {total.toLocaleString()} prefixes</p>
        </div>
      </div>
      <div className="widget-body">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ percent }) => `${(percent * 100).toFixed(0)}%`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
              />
            </PieChart>
          </ResponsiveContainer>

          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: '1rem' }}>
            {chartData.map((item, idx) => (
              <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <div style={{ 
                    width: '12px', 
                    height: '12px', 
                    borderRadius: '2px', 
                    background: item.color 
                  }}></div>
                  <span>{item.name}</span>
                </div>
                <span style={{ fontWeight: '600', fontSize: '1.1rem' }}>
                  {item.value.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>

        {displayData.invalidPrefixes && displayData.invalidPrefixes.length > 0 && (
          <div style={{ marginTop: '1.5rem' }}>
            <h4 style={{ fontSize: '0.9rem', marginBottom: '0.75rem', color: '#8b949e' }}>
              Key Invalid Prefixes
            </h4>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', fontSize: '0.85rem', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #30363d', color: '#8b949e' }}>
                    <th style={{ padding: '0.5rem', textAlign: 'left' }}>Prefix</th>
                    <th style={{ padding: '0.5rem', textAlign: 'left' }}>Origin AS</th>
                    <th style={{ padding: '0.5rem', textAlign: 'left' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(displayData.invalidPrefixes || []).slice(0, 5).map((item, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #30363d' }}>
                      <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>{item.prefix}</td>
                      <td style={{ padding: '0.5rem' }}>AS{item.asn}</td>
                      <td style={{ padding: '0.5rem' }}>
                        <span style={{
                          padding: '0.25rem 0.5rem',
                          borderRadius: '4px',
                          background: 'rgba(248, 81, 73, 0.2)',
                          color: '#f85149',
                          fontSize: '0.75rem',
                          fontWeight: '600'
                        }}>
                          Invalid
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default RpkiSummaryWidget
