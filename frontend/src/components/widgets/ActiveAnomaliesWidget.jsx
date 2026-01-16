import { useState, useEffect } from 'react'
import { getDashboardAnomalies } from '../../api/client'
import { useWebSocketContext } from '../../contexts/WebSocketContext'

function ActiveAnomaliesWidget({ timeRange, filters }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedAnomaly, setSelectedAnomaly] = useState(null)
  
  // WebSocket for real-time updates
  const { anomalies: liveAnomalies, isConnected } = useWebSocketContext()

  // Initial data fetch via HTTP
  useEffect(() => {
    let mounted = true

    const fetchData = async () => {
      try {
        setLoading(true)
        setError(null)
        const result = await getDashboardAnomalies(filters, timeRange)
        if (mounted) {
          setData(result)
          setLoading(false)
        }
      } catch (err) {
        if (mounted) {
          setError(err.message)
          setLoading(false)
        }
      }
    }

    fetchData()
    return () => { mounted = false }
  }, [timeRange, filters])

  // Merge live WebSocket anomalies with fetched data
  const displayAnomalies = data?.anomalies ? [...liveAnomalies, ...data.anomalies] : liveAnomalies
  
  // Remove duplicates based on timestamp + prefix
  const uniqueAnomalies = displayAnomalies.reduce((acc, curr) => {
    const key = `${curr.timestamp}-${curr.prefix}`
    if (!acc.some(a => `${a.timestamp}-${a.prefix}` === key)) {
      acc.push(curr)
    }
    return acc
  }, [])
  
  // Sort by timestamp desc and take latest 10
  const sortedAnomalies = uniqueAnomalies
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .slice(0, 10)

  if (loading && liveAnomalies.length === 0) return <div className="widget"><div className="loading">Loading anomalies...</div></div>
  if (error && !data) return <div className="widget"><div className="error">Error: {error}</div></div>

  // Calculate severity counts from combined data
  const criticalCount = uniqueAnomalies.filter(a => a.severity === 'critical').length
  const highCount = uniqueAnomalies.filter(a => a.severity === 'high').length

  return (
    <div className="widget">
      <div className="widget-header">
        <div>
          <h3 className="widget-title">
            Active Anomalies
            {isConnected && <span style={{ marginLeft: '0.5rem', fontSize: '0.7rem', color: '#3fb950' }}>● LIVE</span>}
          </h3>
          <p className="widget-subtitle">{uniqueAnomalies.length} detected</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', fontSize: '0.85rem' }}>
          <span style={{ color: '#f85149' }}>● {criticalCount} Critical</span>
          <span style={{ color: '#db6d28' }}>● {highCount} High</span>
        </div>
      </div>
      <div className="widget-body">
        <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
          <table style={{ width: '100%', fontSize: '0.85rem', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #30363d', color: '#8b949e' }}>
                <th style={{ padding: '0.5rem', textAlign: 'left', width: '80px' }}>Event ID</th>
                <th style={{ padding: '0.5rem', textAlign: 'left', width: '110px' }}>Timestamp</th>
                <th style={{ padding: '0.5rem', textAlign: 'left' }}>Type</th>
                <th style={{ padding: '0.5rem', textAlign: 'left', width: '90px' }}>Severity</th>
                <th style={{ padding: '0.5rem', textAlign: 'left' }}>Affected</th>
                <th style={{ padding: '0.5rem', textAlign: 'left', width: '90px' }}>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {sortedAnomalies.map((anomaly, idx) => {
                const confidence = anomaly.score ? Math.min(Math.abs(anomaly.score) * 10, 100).toFixed(0) : 0
                const affected = `${anomaly.prefix}${anomaly.asn ? ' | AS' + anomaly.asn : ''}`
                
                return (
                  <tr 
                    key={`${anomaly.timestamp}-${anomaly.prefix}-${idx}`} 
                    style={{ 
                      borderBottom: '1px solid #30363d',
                      cursor: 'pointer',
                      transition: 'background 0.2s'
                    }}
                    onClick={() => setSelectedAnomaly(anomaly)}
                    onMouseEnter={(e) => e.currentTarget.style.background = '#252b3b'}
                    onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.8rem', color: '#8b949e' }}>
                      #{anomaly.id}
                    </td>
                    <td style={{ padding: '0.5rem', fontSize: '0.8rem' }}>
                      {formatTime(anomaly.timestamp)}
                    </td>
                    <td style={{ padding: '0.5rem', fontSize: '0.85rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <span style={{
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          background: getClassificationColor(anomaly.classification),
                          flexShrink: 0
                        }} />
                        <span style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{anomaly.type}</span>
                      </div>
                    </td>
                    <td style={{ padding: '0.5rem' }}>
                      <span style={{ 
                        padding: '0.25rem 0.5rem',
                        borderRadius: '4px',
                        background: getSeverityBg(anomaly.severity),
                        color: getSeverityColor(anomaly.severity),
                        fontSize: '0.75rem',
                        textTransform: 'uppercase'
                      }}>
                        {anomaly.severity}
                      </span>
                    </td>
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                      {affected}
                    </td>
                    <td style={{ padding: '0.5rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                        <div style={{
                          width: '50px',
                          height: '6px',
                          background: '#30363d',
                          borderRadius: '3px',
                          overflow: 'hidden'
                        }}>
                          <div style={{
                            width: `${confidence}%`,
                            height: '100%',
                            background: getConfidenceColor(confidence),
                            transition: 'width 0.3s'
                          }} />
                        </div>
                        <span style={{ fontSize: '0.75rem', color: '#8b949e', minWidth: '32px' }}>
                          {confidence}%
                        </span>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* RCA Panel */}
        {selectedAnomaly && (
          <div style={{
            position: 'fixed',
            top: 0,
            right: 0,
            width: '400px',
            height: '100vh',
            background: '#1a1f2e',
            borderLeft: '1px solid #30363d',
            padding: '2rem',
            overflowY: 'auto',
            zIndex: 1000,
            boxShadow: '-4px 0 12px rgba(0,0,0,0.5)'
          }}>
            <button 
              onClick={() => setSelectedAnomaly(null)}
              style={{
                position: 'absolute',
                top: '1rem',
                right: '1rem',
                background: 'transparent',
                border: 'none',
                color: '#e1e4e8',
                fontSize: '1.5rem',
                cursor: 'pointer'
              }}
            >
              ×
            </button>
            
            <h3 style={{ marginBottom: '1rem' }}>Anomaly Details</h3>
            
            <div style={{ marginBottom: '1.5rem' }}>
              <p style={{ color: '#8b949e', marginBottom: '0.5rem' }}>Event ID</p>
              <p style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>{selectedAnomaly.id}</p>
            </div>

            <div style={{ marginBottom: '1.5rem' }}>
              <p style={{ color: '#8b949e', marginBottom: '0.5rem' }}>Classification</p>
              <p>{selectedAnomaly.classification}</p>
            </div>

            <div style={{ marginBottom: '1.5rem' }}>
              <p style={{ color: '#8b949e', marginBottom: '0.5rem' }}>Metadata</p>
              <pre style={{ 
                background: '#0f1419',
                padding: '0.75rem',
                borderRadius: '4px',
                fontSize: '0.75rem',
                overflow: 'auto'
              }}>
                {JSON.stringify(selectedAnomaly.metadata, null, 2)}
              </pre>
            </div>

            <div>
              <p style={{ color: '#8b949e', marginBottom: '0.75rem' }}>Analyst Actions</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <button style={actionBtnStyle}>✓ Confirmed Threat</button>
                <button style={actionBtnStyle}>✗ False Positive</button>
                <button style={actionBtnStyle}>⚠ Known Issue</button>
                <button style={actionBtnStyle}>🔒 Whitelist</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const actionBtnStyle = {
  padding: '0.75rem',
  background: '#252b3b',
  border: '1px solid #30363d',
  color: '#e1e4e8',
  borderRadius: '4px',
  cursor: 'pointer',
  fontSize: '0.9rem',
  textAlign: 'left'
}

// Format timestamp to UTC time (updated 2026-01-13)
function formatTime(timestamp) {
  if (!timestamp) return 'N/A'
  // Ensure we're working with a Date object
  const date = timestamp instanceof Date ? timestamp : new Date(timestamp)
  
  // Use UTC methods explicitly
  const hours = date.getUTCHours().toString().padStart(2, '0')
  const minutes = date.getUTCMinutes().toString().padStart(2, '0')
  const seconds = date.getUTCSeconds().toString().padStart(2, '0')
  
  return `${hours}:${minutes}:${seconds} UTC`
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

function getSeverityBg(severity) {
  const colors = {
    critical: 'rgba(248, 81, 73, 0.2)',
    high: 'rgba(219, 109, 40, 0.2)',
    medium: 'rgba(210, 153, 34, 0.2)',
    low: 'rgba(63, 185, 80, 0.2)'
  }
  return colors[severity] || 'rgba(139, 148, 158, 0.2)'
}

function getClassificationBg(classification) {
  const colors = {
    HIJACK: '#8b0000',      // Dark red
    LEAK: '#db6d28',        // Orange
    INVALID: '#d29922',     // Yellow
    SUSPICIOUS: '#58a6ff',  // Blue
    NORMAL: '#30363d'       // Gray
  }
  return colors[classification] || '#30363d'
}

function getClassificationColor(classification) {
  const colors = {
    HIJACK: '#f85149',      // Red
    LEAK: '#db6d28',        // Orange
    INVALID: '#d29922',     // Yellow
    SUSPICIOUS: '#58a6ff',  // Blue
    CRITICAL: '#f85149',    // Red
    NORMAL: '#3fb950'       // Green
  }
  return colors[classification] || '#58a6ff'
}

function getConfidenceColor(confidence) {
  if (confidence >= 80) return '#f85149'      // Red - high confidence
  if (confidence >= 60) return '#db6d28'      // Orange - medium-high
  if (confidence >= 40) return '#d29922'      // Yellow - medium
  return '#3fb950'                             // Green - low confidence
}

export default ActiveAnomaliesWidget
