import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store/useStore'
import { getPrefixes, getPrefixDetail } from '../api/client'
import './PrefixForensics.css'

function PrefixForensics() {
  const navigate = useNavigate()
  const { timeRange, filters } = useStore()
  const [prefixes, setPrefixes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedPrefix, setSelectedPrefix] = useState(null)
  const [prefixDetail, setPrefixDetail] = useState(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [lastRefresh, setLastRefresh] = useState(Date.now())

  useEffect(() => {
    fetchPrefixes()
  }, [timeRange, filters, page])

  const fetchPrefixes = async () => {
    try {
      setLoading(true)
      setError(null)
      const result = await getPrefixes(filters, timeRange, page, 50)
      setPrefixes(result.prefixes)
      setTotal(result.total)
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const handleRowClick = async (prefix) => {
    setSelectedPrefix(prefix)
    try {
      const detail = await getPrefixDetail(prefix.prefix, timeRange)
      setPrefixDetail(detail)
    } catch (err) {
      console.error('Failed to fetch prefix detail:', err)
    }
  }

  const handleRefresh = () => {
    setLastRefresh(Date.now())
    fetchPrefixes()
  }

  return (
    <div className="prefix-forensics">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 className="page-title" style={{ margin: 0 }}>Prefix Forensics</h2>
        <button 
          onClick={handleRefresh}
          disabled={loading}
          style={{
            padding: '0.5rem 1rem',
            background: '#238636',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: loading ? 'not-allowed' : 'pointer',
            fontSize: '0.9rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            opacity: loading ? 0.6 : 1
          }}
        >
          🔄 Refresh Data
        </button>
      </div>

      <div className="forensics-container">
        {/* Prefixes Table */}
        <div className="prefixes-table-container">
          {loading ? (
            <div className="loading">Loading prefixes...</div>
          ) : error ? (
            <div className="error">Error: {error}</div>
          ) : (
            <>
              <div className="table-header">
                <span>Showing {prefixes.length} of {total} prefixes</span>
              </div>
              <div className="table-wrapper">
                <table className="prefixes-table">
                  <thead>
                    <tr>
                      <th>Prefix</th>
                      <th>ASN</th>
                      <th>RPKI Status</th>
                      <th>Path Length</th>
                      <th>Flap Count</th>
                      <th>Churn Rate</th>
                      <th>Last Update</th>
                      <th>Anomalies</th>
                      <th>Activity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {prefixes.map((prefix, idx) => (
                      <tr 
                        key={idx}
                        onClick={() => handleRowClick(prefix)}
                        className={selectedPrefix?.prefix === prefix.prefix ? 'selected' : ''}
                      >
                        <td className="prefix-cell">{prefix.prefix}</td>
                        <td>AS{prefix.asn}</td>
                        <td>
                          <span className={`rpki-badge rpki-${prefix.rpkiStatus?.toLowerCase()}`}>
                            {prefix.rpkiStatus}
                          </span>
                        </td>
                        <td>{prefix.pathLength}</td>
                        <td>{prefix.flapCount}</td>
                        <td>{prefix.churnRate}/hr</td>
                        <td>{formatTime(prefix.lastUpdate)}</td>
                        <td>
                          {prefix.anomalyTags?.map((tag, i) => (
                            <span key={i} className="anomaly-tag">{tag}</span>
                          ))}
                        </td>
                        <td>
                          <div className="sparkline">
                            {prefix.sparkline?.map((val, i) => (
                              <div 
                                key={i} 
                                className="sparkline-bar"
                                style={{ height: `${(val / Math.max(...prefix.sparkline)) * 100}%` }}
                              />
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="pagination">
                <button 
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                >
                  Previous
                </button>
                <span>Page {page} of {Math.ceil(total / 50)}</span>
                <button 
                  onClick={() => setPage(p => p + 1)}
                  disabled={page >= Math.ceil(total / 50)}
                >
                  Next
                </button>
              </div>
            </>
          )}
        </div>

        {/* Detail Panel */}
        {selectedPrefix && (
          <div className="detail-panel">
            <div className="detail-header">
              <h3>{selectedPrefix.prefix}</h3>
              <button onClick={() => setSelectedPrefix(null)}>×</button>
            </div>

            <div className="detail-content">
              <div className="detail-section">
                <h4>Prefix Information</h4>
                <div className="detail-row">
                  <span>Origin AS:</span>
                  <span>AS{selectedPrefix.asn}</span>
                </div>
                <div className="detail-row">
                  <span>RPKI Status:</span>
                  <span className={`rpki-badge rpki-${selectedPrefix.rpkiStatus?.toLowerCase()}`}>
                    {selectedPrefix.rpkiStatus}
                  </span>
                </div>
                <div className="detail-row">
                  <span>Path Length:</span>
                  <span>{selectedPrefix.pathLength} hops</span>
                </div>
              </div>

              {prefixDetail?.timeline && (
                <div className="detail-section">
                  <h4>Event Timeline</h4>
                  <div className="timeline">
                    {prefixDetail.timeline.map((event, idx) => (
                      <div key={idx} className="timeline-event">
                        <div className="timeline-time">{formatTime(event.timestamp)}</div>
                        <div className="timeline-content">
                          <strong>{event.type}</strong>
                          <p>{event.description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="detail-actions">
                <button onClick={() => navigate('/path-tracking')}>
                  Open in Path Tracking
                </button>
                <button onClick={() => navigate('/')}>
                  Open in Active Anomalies
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function formatTime(timestamp) {
  if (!timestamp) return 'N/A'
  const date = new Date(timestamp)
  const year = date.getUTCFullYear()
  const month = (date.getUTCMonth() + 1).toString().padStart(2, '0')
  const day = date.getUTCDate().toString().padStart(2, '0')
  const hours = date.getUTCHours().toString().padStart(2, '0')
  const minutes = date.getUTCMinutes().toString().padStart(2, '0')
  const seconds = date.getUTCSeconds().toString().padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds} UTC`
}

export default PrefixForensics
