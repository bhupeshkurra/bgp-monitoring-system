import { create } from 'zustand'

// Global state for filters, time range, and auto-refresh
const useStore = create((set) => ({
  // Time range state
  timeRange: '24h', // Default: 24 hours (to show available data)
  customTimeStart: null,
  customTimeEnd: null,
  
  setTimeRange: (range) => set({ timeRange: range }),
  setCustomTime: (start, end) => set({ customTimeStart: start, customTimeEnd: end }),
  
  // Filter state
  filters: {
    prefix: '',
    asn: '',
    ipVersion: 'all', // 'all', 'ipv4', 'ipv6'
  },
  
  setFilter: (key, value) => set((state) => ({
    filters: { ...state.filters, [key]: value }
  })),
  
  resetFilters: () => set({
    filters: { prefix: '', asn: '', ipVersion: 'all' }
  }),
  
  // Auto-refresh state
  refreshInterval: 60, // seconds (reduced from 30 to minimize refreshing)
  isAutoRefresh: false, // Disabled by default to prevent constant refreshing
  lastRefresh: Date.now(),
  
  setRefreshInterval: (interval) => set({ refreshInterval: interval }),
  toggleAutoRefresh: () => set((state) => ({ isAutoRefresh: !state.isAutoRefresh })),
  triggerRefresh: () => set({ lastRefresh: Date.now() }),
}))

export default useStore
