import { Outlet, NavLink } from 'react-router-dom'
import { useWebSocketContext } from '../contexts/WebSocketContext'
import useStore from '../store/useStore'
import './Layout.css'

function Layout() {
  const { 
    timeRange, setTimeRange, 
    refreshInterval, setRefreshInterval, 
    isAutoRefresh, toggleAutoRefresh, 
    triggerRefresh,
    filters, setFilter, resetFilters 
  } = useStore()
  
  // WebSocket connection status
  const { isConnected, stats } = useWebSocketContext()

  const timePresets = [
    { label: '10m', value: '10m' },
    { label: '15m', value: '15m' },
    { label: '1h', value: '1h' },
    { label: '3h', value: '3h' },
    { label: '12h', value: '12h' },
    { label: '24h', value: '24h' },
    { label: '2d', value: '2d' },
  ]

  const refreshOptions = [15, 30, 45, 60, 120, 300] // seconds

  return (
    <div className="layout">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <h1>🛡️ BGP Monitoring</h1>
        </div>
        <div className="header-right">
          <span className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
            ● {isConnected ? 'Live (WebSocket)' : 'Disconnected'}
          </span>
          {stats && (
            <span style={{ marginLeft: '1rem', fontSize: '0.85rem', color: '#8b949e' }}>
              {stats.total} anomalies (last hour)
            </span>
          )}
        </div>
      </header>

      <div className="main-container">
        {/* Sidebar Navigation */}
        <nav className="sidebar">
          <NavLink to="/" end className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            📊 Dashboard
          </NavLink>
          <NavLink to="/prefix-forensics" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            🔍 Prefix Forensics
          </NavLink>
          <NavLink to="/advanced-analytics" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            📈 Advanced Analytics
          </NavLink>
          <NavLink to="/historical-playback" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            ⏮️ Historical Playback
          </NavLink>
        </nav>

        {/* Main Content */}
        <main className="content">
          {/* Global Controls */}
          <div className="global-controls">
            {/* Time Range Selector */}
            <div className="control-group">
              <label>Time Range:</label>
              <div className="time-presets">
                {timePresets.map(preset => (
                  <button
                    key={preset.value}
                    className={`preset-btn ${timeRange === preset.value ? 'active' : ''}`}
                    onClick={() => setTimeRange(preset.value)}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Filters */}
            <div className="control-group">
              <label>Filters:</label>
              <div className="filters">
                <input
                  type="text"
                  placeholder="Prefix (e.g., 192.0.2.0/24)"
                  value={filters.prefix}
                  onChange={(e) => setFilter('prefix', e.target.value)}
                  className="filter-input"
                />
                <input
                  type="text"
                  placeholder="ASN (e.g., 65000)"
                  value={filters.asn}
                  onChange={(e) => setFilter('asn', e.target.value)}
                  className="filter-input"
                />
                <select
                  value={filters.ipVersion}
                  onChange={(e) => setFilter('ipVersion', e.target.value)}
                  className="filter-select"
                >
                  <option value="all">All IP</option>
                  <option value="ipv4">IPv4</option>
                  <option value="ipv6">IPv6</option>
                </select>
                <button className="reset-btn" onClick={resetFilters}>Reset</button>
              </div>
            </div>

            {/* Auto-refresh */}
            <div className="control-group">
              <label>Auto-refresh:</label>
              <div className="refresh-controls">
                <button 
                  className={`toggle-btn ${isAutoRefresh ? 'active' : ''}`}
                  onClick={toggleAutoRefresh}
                >
                  {isAutoRefresh ? 'ON' : 'OFF'}
                </button>
                <select
                  value={refreshInterval}
                  onChange={(e) => setRefreshInterval(Number(e.target.value))}
                  className="refresh-select"
                  disabled={!isAutoRefresh}
                >
                  {refreshOptions.map(sec => (
                    <option key={sec} value={sec}>
                      {sec < 60 ? `${sec}s` : `${sec/60}m`}
                    </option>
                  ))}
                </select>
                <button className="refresh-btn" onClick={triggerRefresh}>
                  🔄 Refresh
                </button>
              </div>
            </div>
          </div>

          {/* Page Content */}
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default Layout
