# BGP Monitoring System - User Guide

## Overview
Real-time BGP anomaly detection system with multi-source correlation (Heuristic, ML, RPKI) and classification (HIJACK/LEAK/SUSPICIOUS/NORMAL).

**Detection Engines:**
- Heuristic Detector: 7 rule-based detections
- ML Detector: LSTM + Isolation Forest
- RPKI Validator: Routinator integration
- Correlation Engine: Signal fusion and classification

**Data Retention:** 3-day rolling window (automatic cleanup)

---

## Prerequisites

### Required Software
1. **Python 3.11+** - Virtual environment at `.\.venv\`
2. **PostgreSQL 14+** - Database: `bgp_ensemble_db`
3. **Docker Desktop** - For Routinator container
4. **Windows 10/11** - PowerShell required

### Database Configuration
- **Host:** localhost:5432
- **Database:** bgp_ensemble_db
- **User:** postgres
- **Password:** jia091004

---

## Quick Start

### 1. Start Docker Desktop
Ensure Docker Desktop is running before starting services.

### 2. Install Dashboard Dependencies (First Time Only)
```powershell
.\.venv\Scripts\pip.exe install Flask Flask-CORS
```

### 3. Start All Services
```powershell
# Navigate to project directory
cd "E:\synthetic_bgp\routinator + bgp"

# Start Routinator container
docker start routinator

# Start all 6 detection services
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "main.py"
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "feature_aggregator.py"
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "ml_inference_service.py"
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "heuristic_detector.py"
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "rpki_validator_service.py"
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "correlation_engine.py"

# Start Dashboard API Server
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "dashboard_api.py"
```

### 4. Access the Dashboard
Open your browser and navigate to: **http://localhost:5000**

The dashboard provides:
- Real-time detection statistics
- Interactive charts (severity timeline, classification breakdown)
- Search functionality (by prefix or AS)
- Critical alerts feed
- Top affected prefixes and ASNs
- Service health monitoring
- Auto-refresh every 30 seconds

### 5. Verify Services Running
```powershell
# Check Python processes
Get-Process python | Select-Object Id, StartTime | Format-Table

# Check Docker container
docker ps --filter "name=routinator"
```

### 6. Stop All Services
```powershell
# Stop all Python services (including dashboard)
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# Stop Routinator
docker stop routinator
```

---

## Service Details

### 0. dashboard_api.py - Web Dashboard API
**Purpose:** Flask REST API server for web dashboard  
**Database:** Queries all detection tables for visualization  
**Port:** 5000 (HTTP)  
**Endpoints:**
- `/` - Dashboard HTML interface
- `/api/health` - System health check
- `/api/stats` - Summary statistics with time filters
- `/api/detections` - Paginated detection feed
- `/api/timeline` - Time series data for charts
- `/api/alerts` - Critical/high severity alerts
- `/api/search` - Search by prefix or AS
- `/api/services` - Detection services status
**Dashboard Features:**
- 6 interactive charts (line, doughnut, stacked bar)
- Real-time statistics with 1h/24h/7d filters
- Search by prefix/AS
- Top 10 affected prefixes and ASNs
- Service health monitoring
- Auto-refresh every 30 seconds

### 1. main.py - BGP Collector
**Purpose:** Connects to RIS Live WebSocket, collects BGP updates  
**Database:** Writes to `ip_rib` table  
**Log:** N/A (runs in background)  
**Port:** None (WebSocket client)

### 2. feature_aggregator.py - Feature Aggregation
**Purpose:** Aggregates BGP updates into 1-minute windows  
**Database:** Reads `ip_rib`, writes to `bgp_features_1min`  
**State:** Tracks last processed timestamp in `feature_aggregator_state`  
**Poll Interval:** Every 10-30 seconds

### 3. ml_inference_service.py - ML Detection
**Purpose:** LSTM + Isolation Forest anomaly detection  
**Database:** Reads `bgp_features_1min`, writes to `hybrid_anomaly_detections`  
**Models:** 
- `lstm_bgp_model.keras` (LSTM autoencoder)
- `isolation_forest_model.pkl` (Isolation Forest)
- `scaler_lstm.pkl`, `scaler_if.pkl`, `baseline_stats.json`
**Poll Interval:** Every 15 seconds

### 4. heuristic_detector.py - Rule-Based Detection
**Purpose:** 7 heuristic rules (churn, flapping, path length, etc.)  
**Database:** Reads `bgp_features_1min`, writes to `hybrid_anomaly_detections`  
**Log:** `heuristic.log`  
**Poll Interval:** Every 20 seconds

**Detection Rules:**
- High churn (>1212 updates/min)
- Route flapping (>132 flaps/min)
- Path length anomaly (>16 hops)
- Origin change detection
- Withdrawal spike (>70% withdrawals)
- Prefix volume spike
- Session instability

### 5. rpki_validator_service.py - RPKI Validation
**Purpose:** Validates BGP routes against RPKI using Routinator  
**Database:** Reads `bgp_features_1min`, writes to `hybrid_anomaly_detections`  
**Log:** `rpki_validator.log`  
**Routinator API:** http://localhost:8323/api/v1/validity  
**Poll Interval:** Every 30 seconds  
**Startup:** Waits up to 60 seconds for Routinator initialization

**Detection Types:**
- **Invalid:** RPKI origin AS mismatch (Critical → HIJACK)
- **MaxLength:** Prefix length exceeds MaxLength (High → LEAK)
- **Unknown:** No ROA found (Low → informational)

### 6. correlation_engine.py - Signal Fusion
**Purpose:** Correlates detections from 3 engines, applies classification  
**Database:** Reads `hybrid_anomaly_detections`, updates classifications  
**Log:** `correlation_engine.log`  
**Poll Interval:** Every 20 seconds

**Classifications:**
- **HIJACK:** RPKI origin mismatch (Critical)
- **LEAK:** RPKI MaxLength violation (High)
- **INVALID:** RPKI validation failed (High)
- **SUSPICIOUS:** Multiple sources detected (Medium/High)
- **NORMAL:** Single weak signal (Low)

---

## Database Schema

### Key Tables

**ip_rib** (Raw BGP updates)
- 781K+ rows, ~157 MB
- Columns: timestamp, peer_ip, peer_asn, prefix, origin_as, as_path, next_hop, iswithdrawn

**bgp_features_1min** (Aggregated features)
- 1-minute windows
- Columns: window_start, prefix, origin_as, path_length, announcements, withdrawals, unique_peers

**hybrid_anomaly_detections** (All detections)
- 100K+ rows, ~62 MB
- Columns: id, timestamp, detection_id, prefix, origin_as, event_type, rpki_status, rpki_anomaly, classification, combined_severity, combined_score, metadata

**correlated_detections** (Final results - future use)
- Currently unused, reserved for future enhancements

**State Tables:**
- `heuristic_inference_state` - Heuristic progress tracking
- `ml_inference_state` - ML progress tracking
- `rpki_inference_state` - RPKI progress tracking
- `correlation_engine_state` - Correlation progress (last_processed_id)

---

## Data Retention

**Automatic Cleanup:** Windows Task Scheduler runs daily at 2 AM (or on next boot if missed)

**Task Name:** BGP_Cleanup_3Day

**Retention Policy:** 3-day rolling window (data deleted after 3 days)

**Tables Cleaned:**
- ip_rib
- bgp_features_1min
- bgp_features_5min
- hybrid_anomaly_detections
- correlated_detections
- ip_rib_log

**Verify Task:**
```powershell
Get-ScheduledTask -TaskName "BGP_Cleanup_3Day" | Get-ScheduledTaskInfo
```

**Manual Cleanup:**
```powershell
.\.venv\Scripts\python.exe cleanup_old_data.py
```

---

## Monitoring & Troubleshooting

### Check Service Health
```powershell
# View running services
Get-Process python | Select-Object Id, @{Name='Runtime';Expression={(Get-Date) - $_.StartTime}} | Format-Table

# Check Docker
docker ps --filter "name=routinator"

# Check logs
Get-Content rpki_validator.log -Tail 20
Get-Content correlation_engine.log -Tail 20
```

### View Detection Statistics
```sql
-- Connect to database
$env:PGPASSWORD='jia091004'; psql -U postgres -d bgp_ensemble_db

-- Total detections by classification
SELECT classification, combined_severity, COUNT(*) 
FROM hybrid_anomaly_detections 
GROUP BY classification, combined_severity 
ORDER BY classification, combined_severity;

-- Recent detections (last hour)
SELECT timestamp, prefix, origin_as, classification, combined_severity, event_type
FROM hybrid_anomaly_detections
WHERE timestamp > NOW() - INTERVAL '1 hour'
ORDER BY timestamp DESC
LIMIT 20;

-- Detection rate
SELECT DATE_TRUNC('hour', timestamp) as hour, COUNT(*) as detections
FROM hybrid_anomaly_detections
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;
```

### Common Issues

**Issue: Services not collecting data**
- Check if Docker is running: `docker ps`
- Verify Routinator: `docker logs routinator`
- Check database connection: `psql -U postgres -d bgp_ensemble_db -c "SELECT 1"`

**Issue: RPKI validator errors**
- Routinator needs 30-60 seconds to initialize after Docker starts
- Wait for "Routinator is ready" message in rpki_validator.log
- Restart service if it exited early

**Issue: Correlation engine slow/hanging**
- First run processes backlog (2-5 minutes for ~2500 detections)
- Subsequent runs are fast (5-10 seconds)
- Check correlation_engine.log for progress messages

**Issue: Disk space filling up**
- Verify cleanup task is scheduled: `Get-ScheduledTask BGP_Cleanup_3Day`
- Manually run cleanup: `.\.venv\Scripts\python.exe cleanup_old_data.py`
- Check data age: `SELECT MIN(timestamp), MAX(timestamp) FROM ip_rib;`

---

## Configuration

### Detection Thresholds

Edit `heuristic_detector.py` for custom thresholds:
```python
# Line ~50
THRESHOLDS = {
    'churn': {'moderate': 1212, 'severe': 6012, 'critical': 24000},
    'flapping': {'medium': 132, 'high': 372, 'critical': 1200},
    'path_length': {'mild': 16, 'severe': 25}
}
```

### Poll Intervals

Adjust service polling frequency:
- `feature_aggregator.py`: Line ~20, `POLL_INTERVAL`
- `ml_inference_service.py`: Line ~30, `POLL_INTERVAL`
- `heuristic_detector.py`: Line ~40, `POLL_INTERVAL`
- `rpki_validator_service.py`: Line ~39, `POLL_INTERVAL`
- `correlation_engine.py`: Line ~25, `POLL_INTERVAL`

### Data Retention

Edit `cleanup_old_data.py`:
```python
# Line 31
RETENTION_DAYS = 3  # Change to desired number of days
```

---

## System Architecture

```
RIS Live → main.py → ip_rib → feature_aggregator → bgp_features_1min
                                                           ↓
                                    ┌──────────────────────┼──────────────────────┐
                                    ↓                      ↓                      ↓
                            heuristic_detector    ml_inference_service    rpki_validator
                                    ↓                      ↓                      ↓
                                    └──────────────────────┼──────────────────────┘
                                                           ↓
                                              hybrid_anomaly_detections
                                                           ↓
                                                  correlation_engine
                                                   (classification)
```

---

## File Structure

```
E:\synthetic_bgp\routinator + bgp\
│
├── main.py                      # BGP collector (RIS Live)
├── feature_aggregator.py        # 1-minute aggregation
├── ml_inference_service.py      # LSTM + Isolation Forest
├── heuristic_detector.py        # Rule-based detection
├── rpki_validator_service.py    # RPKI validation
├── correlation_engine.py        # Signal fusion
├── cleanup_old_data.py          # Data retention
│
├── .venv\                       # Python virtual environment
│   └── Scripts\python.exe       # Python 3.11 interpreter
│
├── Models & Artifacts
│   ├── lstm_bgp_model.keras     # LSTM model
│   ├── isolation_forest_model.pkl
│   ├── scaler_lstm.pkl
│   ├── scaler_if.pkl
│   └── baseline_stats.json
│
├── Documentation
│   ├── README.md                # This file
│   └── Bgp Monitoring System — Technical Design 4 (1).txt
│
├── Dashboard
│   ├── dashboard_api.py         # Flask REST API server
│   └── dashboard.html           # Advanced web dashboard
│
├── Logs (created at runtime)
│   ├── rpki_validator.log
│   ├── correlation_engine.log
│   ├── cleanup.log
│   └── heuristic.log
│
└── archive_old_scripts\         # Old/backup scripts
```

---

## Technical Specifications

**System Requirements:**
- CPU: 4+ cores recommended
- RAM: 8 GB minimum, 16 GB recommended
- Disk: 10 GB free space (for 3-day retention)
- Network: Stable internet for RIS Live connection

**Database Size (3-day retention):**
- ip_rib: ~120 MB/day → 360 MB
- hybrid_anomaly_detections: ~56 MB/day → 168 MB
- Total: ~528 MB steady state

**Performance:**
- BGP updates/sec: ~10-50
- Detections/hour: ~100-500
- Correlation latency: 20-60 seconds end-to-end

**Timezone:** Asia/Calcutta (GMT+5:30)

---

## Support & Maintenance

**Scheduled Tasks:**
- Data cleanup: Daily at 2 AM (BGP_Cleanup_3Day)

**Regular Checks:**
- Monitor disk space weekly
- Review detection counts daily
- Check service logs for errors

**Backup Recommendations:**
- Database: Weekly full backup of bgp_ensemble_db
- Models: Keep backups of .keras/.pkl files
- Logs: Archive monthly for audit trail

---

## Project Status

✅ **Phase 1-4 Complete:**
- Data collection (RIS Live)
- Detection engines (Heuristic, ML, RPKI)
- Correlation & classification
- Data retention (3-day rolling window)
- Web Dashboard with advanced visualization

**System Ready for Production Deployment**

---

## Contact & Credits

**Project:** BGP Anomaly Detection & Classification System  
**Version:** v1.0 (Phase 3 Complete)  
**Date:** January 8, 2026

---

## Quick Reference Commands

```powershell
# Start all services (including dashboard)
docker start routinator
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "main.py"
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "feature_aggregator.py"
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "ml_inference_service.py"
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "heuristic_detector.py"
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "rpki_validator_service.py"
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "correlation_engine.py"
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "dashboard_api.py"

# Open dashboard in browser
Start-Process "http://localhost:5000"

# Stop all services
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
docker stop routinator

# Check status
Get-Process python | Select-Object Id, @{Name='Runtime';Expression={(Get-Date) - $_.StartTime}}
docker ps --filter "name=routinator"

# View logs
Get-Content rpki_validator.log -Tail 20
Get-Content correlation_engine.log -Tail 20

# Database queries
$env:PGPASSWORD='jia091004'; psql -U postgres -d bgp_ensemble_db -c "SELECT COUNT(*) FROM hybrid_anomaly_detections WHERE timestamp > NOW() - INTERVAL '1 hour';"
```
