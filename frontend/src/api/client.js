import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Helper to build query params from filters and time range
const buildParams = (filters, timeRange) => {
  const params = {}
  
  if (filters.prefix) params.prefix = filters.prefix
  if (filters.asn) params.asn = filters.asn
  if (filters.ipVersion !== 'all') params.ip_version = filters.ipVersion
  if (timeRange) params.time_range = timeRange
  
  return params
}

// ===== Dashboard APIs =====

export const getDashboardChurn = async (filters, timeRange) => {
  // GET /api/dashboard/churn?time_range=1h&prefix=...
  const response = await api.get('/dashboard/churn', {
    params: buildParams(filters, timeRange)
  })
  return response.data
}

export const getDashboardAnomalies = async (filters, timeRange) => {
  // GET /api/dashboard/anomalies?time_range=1h
  const response = await api.get('/dashboard/anomalies', {
    params: buildParams(filters, timeRange)
  })
  return response.data
}

export const getDashboardFlaps = async (filters, timeRange) => {
  // GET /api/dashboard/flaps?time_range=1h
  const response = await api.get('/dashboard/flaps', {
    params: buildParams(filters, timeRange)
  })
  return response.data
}

export const getMessageVolume = async (filters, timeRange) => {
  // GET /api/dashboard/message-volume?time_range=1h
  const response = await api.get('/dashboard/message-volume', {
    params: buildParams(filters, timeRange)
  })
  return response.data
}

export const getRpkiSummary = async (filters, timeRange) => {
  // GET /api/dashboard/rpki-summary?time_range=1h
  const response = await api.get('/dashboard/rpki-summary', {
    params: buildParams(filters, timeRange)
  })
  return response.data
}

// ===== Prefix Forensics APIs =====

export const getPrefixes = async (filters, timeRange, page = 1, limit = 50) => {
  // GET /api/prefixes?page=1&limit=50&prefix=...
  const response = await api.get('/prefixes', {
    params: { ...buildParams(filters, timeRange), page, limit }
  })
  return response.data
}

export const getPrefixDetail = async (prefix, timeRange) => {
  // GET /api/prefixes/:prefix?time_range=1h
  const response = await api.get(`/prefixes/${encodeURIComponent(prefix)}`, {
    params: { time_range: timeRange }
  })
  return response.data
}

// ===== Advanced Analytics APIs =====

export const getAnalytics = async (filters, timeRange) => {
  // GET /api/analytics?time_range=1h
  const response = await api.get('/analytics', {
    params: buildParams(filters, timeRange)
  })
  return response.data
}

// ===== Historical Playback APIs =====

export const getHistoricalData = async (startTime, endTime, granularity = '5m') => {
  // GET /api/historical?start=...&end=...&granularity=5m
  const response = await api.get('/historical', {
    params: { start: startTime, end: endTime, granularity }
  })
  return response.data
}

export default api
