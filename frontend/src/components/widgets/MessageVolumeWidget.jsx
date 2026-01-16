import { useState, useEffect } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { useWebSocketContext } from '../../contexts/WebSocketContext'

function MessageVolumeWidget({ timeRange, filters }) {
  const { dashboardData, isConnected } = useWebSocketContext()
  const [loading, setLoading] = useState(true)

  const displayData = dashboardData?.volume || null

  useEffect(() => {
    if (displayData) {
      setLoading(false)
    }
  }, [displayData])

  if (loading && !displayData) return <div className="widget"><div className="loading">Loading volume data...</div></div>
  if (!displayData) return <div className="widget"><div className="loading">No data</div></div>

  return (
    <div className="widget">
      <div className="widget-header">
        <div>
          <h3 className="widget-title">
            Message Volume Trend
            {isConnected && <span style={{ marginLeft: '0.5rem', fontSize: '0.7rem', color: '#3fb950' }}>● LIVE</span>}
          </h3>
          <p className="widget-subtitle">BGP messages per minute</p>
        </div>
        <div style={{ fontSize: '0.85rem', color: '#8b949e' }}>
          Avg: {displayData.averageVolume?.toFixed(0)} msg/min
        </div>
      </div>
      <div className="widget-body">
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={displayData.timeSeries}>
            <defs>
              <linearGradient id="volumeGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#58a6ff" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#58a6ff" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
            <XAxis dataKey="time" stroke="#8b949e" />
            <YAxis stroke="#8b949e" />
            <Tooltip 
              contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
              labelStyle={{ color: '#e1e4e8' }}
            />
            {displayData.threshold && (
              <ReferenceLine 
                y={displayData.threshold} 
                stroke="#f85149" 
                strokeDasharray="5 5" 
                label="Threshold" 
              />
            )}
            <Area 
              type="monotone" 
              dataKey="volume" 
              stroke="#58a6ff" 
              fillOpacity={1}
              fill="url(#volumeGradient)"
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>

        {displayData.anomalies?.length > 0 && (
          <div style={{ marginTop: '1rem' }}>
            <h4 style={{ fontSize: '0.9rem', marginBottom: '0.75rem', color: '#8b949e' }}>
              Detected Volume Spikes
            </h4>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {displayData.anomalies.map((anomaly, idx) => (
                <div key={idx} style={{
                  background: 'rgba(248, 81, 73, 0.2)',
                  border: '1px solid rgba(248, 81, 73, 0.3)',
                  padding: '0.5rem 0.75rem',
                  borderRadius: '4px',
                  fontSize: '0.8rem'
                }}>
                  {anomaly.time}: {anomaly.volume} msg/min
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default MessageVolumeWidget
