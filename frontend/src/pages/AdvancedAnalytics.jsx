import { useState, useEffect } from 'react'
import { LineChart, Line, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from 'recharts'
import useStore from '../store/useStore'
import { getAnalytics } from '../api/client'
import './AdvancedAnalytics.css'

function AdvancedAnalytics() {
  const { timeRange, filters } = useStore()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastRefresh, setLastRefresh] = useState(Date.now())

  useEffect(() => {
    fetchAnalytics()
  }, [timeRange, filters])

  const fetchAnalytics = async () => {
    try {
      setLoading(true)
      setError(null)
      const result = await getAnalytics(filters, timeRange)
      setData(result)
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  if (loading) return <div className="loading-page">Loading analytics...</div>
  if (error) return <div className="error-page">Error: {error}</div>
  if (!data) return <div className="loading-page">No data</div>

  const handleRefresh = () => {
    setLastRefresh(Date.now())
    fetchAnalytics()
  }

  return (
    <div className="advanced-analytics">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 className="page-title" style={{ margin: 0 }}>Advanced Analytics</h2>
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

      <div className="analytics-grid">
        {/* Anomaly Trends */}
        <div className="analytics-card">
          <h3>Anomaly Trends vs Baseline</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data.anomalyTrends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="time" stroke="#8b949e" />
              <YAxis stroke="#8b949e" />
              <Tooltip 
                contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
              />
              <Legend />
              <ReferenceLine y={data.baseline} stroke="#8b949e" strokeDasharray="5 5" label="Baseline" />
              <Line type="monotone" dataKey="anomalyScore" stroke="#f85149" strokeWidth={2} name="Anomaly Score" />
              <Line type="monotone" dataKey="count" stroke="#58a6ff" strokeWidth={2} name="Count" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Prefix Behavior Scatter */}
        <div className="analytics-card">
          <h3>Prefix Behavior Analysis</h3>
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="updateRate" name="Update Rate" stroke="#8b949e" />
              <YAxis dataKey="withdrawalRate" name="Withdrawal Rate" stroke="#8b949e" />
              <Tooltip 
                contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
                cursor={{ strokeDasharray: '3 3' }}
              />
              <Scatter name="Prefixes" data={data.prefixBehavior} fill="#58a6ff" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>

        {/* Traffic Correlation */}
        <div className="analytics-card">
          <h3>Traffic vs Anomaly Correlation</h3>
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="traffic" name="Traffic Volume" stroke="#8b949e" />
              <YAxis dataKey="anomalyCount" name="Anomaly Count" stroke="#8b949e" />
              <Tooltip 
                contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
                cursor={{ strokeDasharray: '3 3' }}
              />
              <Scatter 
                name="Correlation" 
                data={data.trafficCorrelation} 
                fill="#3fb950"
              />
            </ScatterChart>
          </ResponsiveContainer>
          <div className="chart-legend">
            Bubble size represents severity level
          </div>
        </div>

        {/* RPKI Trends */}
        <div className="analytics-card">
          <h3>RPKI Validation Trends</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data.rpkiTrends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="time" stroke="#8b949e" />
              <YAxis stroke="#8b949e" />
              <Tooltip 
                contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
              />
              <Legend />
              <Line type="monotone" dataKey="valid" stroke="#3fb950" strokeWidth={2} name="Valid" />
              <Line type="monotone" dataKey="invalid" stroke="#f85149" strokeWidth={2} name="Invalid" />
              <Line type="monotone" dataKey="unknown" stroke="#d29922" strokeWidth={2} name="Unknown" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Summary Stats */}
        <div className="analytics-card stats-card">
          <h3>Summary Statistics</h3>
          <div className="stats-grid">
            <div className="stat-item">
              <div className="stat-label">Total Anomalies</div>
              <div className="stat-value">{data.stats?.totalAnomalies || 0}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Critical Events</div>
              <div className="stat-value critical">{data.stats?.criticalCount || 0}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Avg Anomaly Score</div>
              <div className="stat-value">{data.stats?.avgScore?.toFixed(2) || '0.00'}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Detection Rate</div>
              <div className="stat-value">{data.stats?.detectionRate || '0%'}</div>
            </div>
          </div>
        </div>

        {/* Top ASNs */}
        <div className="analytics-card">
          <h3>Top ASNs by Activity</h3>
          <div className="top-list">
            {data.topAsns?.map((asn, idx) => (
              <div key={idx} className="top-list-item">
                <div className="rank">#{idx + 1}</div>
                <div className="asn-info">
                  <div className="asn-name">AS{asn.asn}</div>
                  <div className="asn-stats">
                    {asn.updates} updates • {asn.anomalies} anomalies
                  </div>
                </div>
                <div className="activity-bar">
                  <div 
                    className="activity-fill"
                    style={{ 
                      width: `${(asn.updates / Math.max(...data.topAsns.map(a => a.updates))) * 100}%`,
                      background: asn.anomalies > 0 ? '#f85149' : '#3fb950'
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export default AdvancedAnalytics
