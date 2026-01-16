import { useState, useEffect } from 'react'
import useStore from '../store/useStore'
import ChurnSummaryWidget from '../components/widgets/ChurnSummaryWidget'
import ActiveAnomaliesWidget from '../components/widgets/ActiveAnomaliesWidget'
import RouteFlapWidget from '../components/widgets/RouteFlapWidget'
import MessageVolumeWidget from '../components/widgets/MessageVolumeWidget'
import RpkiSummaryWidget from '../components/widgets/RpkiSummaryWidget'
import './Dashboard.css'

function Dashboard() {
  const { timeRange, filters, lastRefresh } = useStore()
  const [refreshKey, setRefreshKey] = useState(0)

  // Manual refresh only (WebSocket handles auto-updates)
  useEffect(() => {
    setRefreshKey(prev => prev + 1)
  }, [lastRefresh])

  return (
    <div className="dashboard">
      <h2 className="page-title">Dashboard Overview</h2>
      
      <div className="widgets-grid">
        <ChurnSummaryWidget key={`churn-${refreshKey}`} timeRange={timeRange} filters={filters} />
        <ActiveAnomaliesWidget key={`anomalies-${refreshKey}`} timeRange={timeRange} filters={filters} />
        <RouteFlapWidget key={`flaps-${refreshKey}`} timeRange={timeRange} filters={filters} />
        <MessageVolumeWidget key={`volume-${refreshKey}`} timeRange={timeRange} filters={filters} />
        <RpkiSummaryWidget key={`rpki-${refreshKey}`} timeRange={timeRange} filters={filters} />
      </div>
    </div>
  )
}

export default Dashboard
