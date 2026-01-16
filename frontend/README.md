# BGP Monitoring Dashboard

Modern React-based dashboard for BGP anomaly detection and network monitoring.

## ✨ Features Implemented (12/12)

### Dashboard Page
1. **Churn Summary Widget** - Announcements vs Withdrawals with top churning prefixes
2. **Active Anomalies Widget** - Real-time anomaly detection with RCA panel
3. **Route Flap Widget** - Flap rate monitoring with alerts
4. **Message Volume Widget** - BGP message volume trends with spike detection
5. **RPKI Summary Widget** - RPKI validation status (Valid/Invalid/Unknown)

### Pages
6. **Prefix Forensics** - Detailed prefix analysis with filtering and drill-down
7. **Advanced Analytics** - Anomaly trends, correlation analysis, and statistics
8. **Historical Playback** - Time-travel through historical BGP data

### Global Features
9. **Time Range Selector** - 10m, 15m, 1h, 3h, 12h, 24h, 7d, 14d, 30d
10. **Auto-refresh** - Configurable intervals (15s, 30s, 45s, 1m, 2m, 5m)
11. **Prefix/ASN Filtering** - Filter by prefix, ASN, IP version
12. **IPv4/IPv6 Toggle** - Filter by IP version

## 🚀 Quick Start

### Installation

```bash
cd frontend
npm install
```

### Development

```bash
npm run dev
```

Dashboard will run on `http://localhost:3000`

### Build for Production

```bash
npm run build
npm run preview
```

## 📁 Project Structure

```
frontend/
├── src/
│   ├── api/
│   │   └── client.js          # API layer for backend calls
│   ├── components/
│   │   ├── Layout.jsx          # Main layout with navigation
│   │   ├── Layout.css
│   │   └── widgets/            # Dashboard widgets
│   │       ├── ChurnSummaryWidget.jsx
│   │       ├── ActiveAnomaliesWidget.jsx
│   │       ├── RouteFlapWidget.jsx
│   │       ├── MessageVolumeWidget.jsx
│   │       └── RpkiSummaryWidget.jsx
│   ├── pages/
│   │   ├── Dashboard.jsx       # Main dashboard page
│   │   ├── PrefixForensics.jsx # Prefix analysis page
│   │   ├── AdvancedAnalytics.jsx # Analytics visualizations
│   │   └── HistoricalPlayback.jsx # Time playback
│   ├── store/
│   │   └── useStore.js         # Global state (Zustand)
│   ├── App.jsx                 # Main app component
│   ├── main.jsx                # Entry point
│   └── index.css               # Global styles
├── public/
├── index.html
├── package.json
└── vite.config.js
```

## 🔌 Backend Integration

### API Endpoints Required

The dashboard expects these API endpoints on `http://localhost:5000/api`:

#### Dashboard
- `GET /api/dashboard/churn?time_range=1h&prefix=...`
- `GET /api/dashboard/anomalies?time_range=1h`
- `GET /api/dashboard/flaps?time_range=1h`
- `GET /api/dashboard/message-volume?time_range=1h`
- `GET /api/dashboard/rpki-summary?time_range=1h`

#### Prefix Forensics
- `GET /api/prefixes?page=1&limit=50&prefix=...&asn=...`
- `GET /api/prefixes/:prefix?time_range=1h`

#### Analytics
- `GET /api/analytics?time_range=1h`

#### Historical
- `GET /api/historical?start=...&end=...&granularity=5m`

### Expected Response Formats

See `src/api/client.js` for detailed TypeScript-style interfaces in comments.

## 🎨 Design System

### Color Scheme (Dark Theme)
- **Background**: `#0f1419` (primary), `#1a1f2e` (secondary), `#252b3b` (tertiary)
- **Text**: `#e1e4e8` (primary), `#8b949e` (secondary)
- **Accents**:
  - Blue: `#58a6ff` (info/links)
  - Green: `#3fb950` (success/valid)
  - Yellow: `#d29922` (warning/unknown)
  - Orange: `#db6d28` (high severity)
  - Red: `#f85149` (critical/invalid)

### Typography
- Font: System fonts (Apple, SF Pro, Segoe UI, Roboto)
- Monospace for: prefixes, ASNs, event IDs

## 🛠️ Technology Stack

- **Framework**: React 18
- **Build Tool**: Vite
- **Router**: React Router v6
- **Charts**: Recharts
- **State**: Zustand
- **HTTP Client**: Axios
- **Date Handling**: date-fns

## 📊 Widget Details

### Churn Summary
- Dual-line chart (announcements vs withdrawals)
- Top 5 churning prefixes with severity badges
- Severity-based color coding

### Active Anomalies
- Paginated anomaly table
- Click-to-open RCA panel
- Analyst action buttons (stub handlers)

### Route Flap
- Time-series with threshold line
- Alert banners for high flap rates
- Per-prefix/peer flap tracking

### Message Volume
- Area chart with gradient fill
- Threshold line and anomaly markers
- Average volume display

### RPKI Summary
- Pie chart of validation status
- Summary statistics
- Table of invalid prefixes

## 🔧 Customization

### Add New Widget

1. Create widget component in `src/components/widgets/`
2. Import in `Dashboard.jsx`
3. Add to widgets grid
4. Create corresponding API endpoint

### Modify Time Presets

Edit `src/components/Layout.jsx`:
```javascript
const timePresets = [
  { label: '10m', value: '10m' },
  // Add more...
]
```

### Change Auto-refresh Intervals

Edit `src/components/Layout.jsx`:
```javascript
const refreshOptions = [15, 30, 45, 60, 120, 300] // seconds
```

## 📝 Notes

- All widgets auto-refresh based on global settings
- Filters and time range are shared across all pages
- State persists during navigation
- Backend URL is proxied through Vite (see `vite.config.js`)

## 🐛 Troubleshooting

**Dashboard not loading?**
- Check backend is running on port 5000
- Verify API endpoints are accessible
- Check browser console for errors

**Charts not displaying?**
- Ensure data format matches expected schema
- Check response has `timeSeries` array
- Verify numeric values aren't strings

**Filters not working?**
- Check global state in React DevTools
- Verify API accepts query parameters
- Check filter values are being passed correctly

## 📄 License

Part of BGP Monitoring System - Internal Use
