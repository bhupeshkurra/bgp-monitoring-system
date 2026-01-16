import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { getHistoricalData } from '../api/client'
import './HistoricalPlayback.css'

function HistoricalPlayback() {
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [maxTime, setMaxTime] = useState(100)
  const [playbackSpeed, setPlaybackSpeed] = useState(1)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchHistoricalData()
  }, [])

  useEffect(() => {
    if (!isPlaying) return

    const interval = setInterval(() => {
      setCurrentTime(prev => {
        if (prev >= maxTime) {
          setIsPlaying(false)
          return maxTime
        }
        return prev + 1
      })
    }, 1000 / playbackSpeed)

    return () => clearInterval(interval)
  }, [isPlaying, maxTime, playbackSpeed])

  const fetchHistoricalData = async () => {
    try {
      setLoading(true)
      const endTime = new Date().toISOString()
      const startTime = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
      const result = await getHistoricalData(startTime, endTime, '5m')
      setData(result)
      setMaxTime(result.timeSeries?.length || 100)
      setLoading(false)
    } catch (err) {
      console.error('Failed to fetch historical data:', err)
      setLoading(false)
    }
  }

  const handlePlayPause = () => {
    setIsPlaying(!isPlaying)
  }

  const handleReset = () => {
    setCurrentTime(0)
    setIsPlaying(false)
  }

  const getCurrentData = () => {
    if (!data?.timeSeries) return []
    return data.timeSeries.slice(0, currentTime + 1)
  }

  if (loading) return <div className="loading-page">Loading historical data...</div>

  return (
    <div className="historical-playback">
      <h2 className="page-title">Historical Playback</h2>

      {/* Playback Controls */}
      <div className="playback-controls">
        <div className="control-buttons">
          <button onClick={handleReset} className="control-btn">⏮️ Reset</button>
          <button onClick={handlePlayPause} className="control-btn primary">
            {isPlaying ? '⏸️ Pause' : '▶️ Play'}
          </button>
        </div>

        <div className="speed-control">
          <label>Speed:</label>
          <select value={playbackSpeed} onChange={(e) => setPlaybackSpeed(Number(e.target.value))}>
            <option value={0.5}>0.5x</option>
            <option value={1}>1x</option>
            <option value={2}>2x</option>
            <option value={5}>5x</option>
            <option value={10}>10x</option>
          </select>
        </div>

        <div className="time-display">
          {getCurrentTimeLabel(currentTime, data?.timeSeries)}
        </div>
      </div>

      {/* Time Scrubber */}
      <div className="scrubber-container">
        <input
          type="range"
          min="0"
          max={maxTime}
          value={currentTime}
          onChange={(e) => setCurrentTime(Number(e.target.value))}
          className="time-scrubber"
        />
        <div className="scrubber-labels">
          <span>Start</span>
          <span>{currentTime} / {maxTime}</span>
          <span>End</span>
        </div>
      </div>

      {/* Mini Charts */}
      <div className="charts-grid">
        {/* Churn Chart */}
        <div className="playback-chart">
          <h3>Churn Activity</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={getCurrentData()}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="time" stroke="#8b949e" />
              <YAxis stroke="#8b949e" />
              <Tooltip 
                contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
              />
              <Legend />
              <Line type="monotone" dataKey="announcements" stroke="#3fb950" strokeWidth={2} />
              <Line type="monotone" dataKey="withdrawals" stroke="#f85149" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Flaps Chart */}
        <div className="playback-chart">
          <h3>Route Flaps</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={getCurrentData()}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="time" stroke="#8b949e" />
              <YAxis stroke="#8b949e" />
              <Tooltip 
                contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
              />
              <Line type="monotone" dataKey="flaps" stroke="#58a6ff" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Message Volume Chart */}
        <div className="playback-chart">
          <h3>Message Volume</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={getCurrentData()}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="time" stroke="#8b949e" />
              <YAxis stroke="#8b949e" />
              <Tooltip 
                contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
              />
              <Line type="monotone" dataKey="messageVolume" stroke="#d29922" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Anomaly Count Chart */}
        <div className="playback-chart">
          <h3>Anomaly Count</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={getCurrentData()}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="time" stroke="#8b949e" />
              <YAxis stroke="#8b949e" />
              <Tooltip 
                contentStyle={{ background: '#1a1f2e', border: '1px solid #30363d' }}
              />
              <Line type="monotone" dataKey="anomalies" stroke="#f85149" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Current Stats */}
      <div className="current-stats">
        <h3>Current Snapshot</h3>
        <div className="stats-row">
          <div className="stat-box">
            <div className="stat-label">Announcements</div>
            <div className="stat-value">{data?.timeSeries?.[currentTime]?.announcements || 0}</div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Withdrawals</div>
            <div className="stat-value">{data?.timeSeries?.[currentTime]?.withdrawals || 0}</div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Flaps</div>
            <div className="stat-value">{data?.timeSeries?.[currentTime]?.flaps || 0}</div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Anomalies</div>
            <div className="stat-value critical">{data?.timeSeries?.[currentTime]?.anomalies || 0}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

function getCurrentTimeLabel(index, timeSeries) {
  if (!timeSeries || !timeSeries[index]) return 'N/A'
  return timeSeries[index].time
}

export default HistoricalPlayback
