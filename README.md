# BGP Monitoring & Anomaly Detection System

A real-time BGP (Border Gateway Protocol) monitoring system that collects live Internet routing data from RIPE RIS, validates routes using RPKI, and detects anomalies using machine learning (LSTM + Isolation Forest) and heuristic methods.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)

## 🌟 Features

- **Live BGP Data Collection** - Real-time BGP updates from RIPE RIS Live WebSocket
- **RPKI Validation** - Route origin validation using Routinator RPKI validator
- **Machine Learning Detection** - LSTM neural network + Isolation Forest for anomaly detection
- **Heuristic Analysis** - Rule-based detection for BGP hijacks, route leaks, and instability
- **Real-time Dashboard** - React-based web interface with live anomaly alerts
- **Historical Playback** - Analyze past BGP events and anomalies
- **Multi-table Support** - IPv4/IPv6 Internet routes + MPLS L3VPN routes

## 📋 Table of Contents

- [System Architecture](#system-architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the System](#running-the-system)
- [Dashboard Access](#dashboard-access)
- [Project Structure](#project-structure)
- [API Documentation](#api-documentation)
- [Troubleshooting](#troubleshooting)

## 🏗️ System Architecture

```
┌─────────────────┐
│   RIPE RIS Live │ ──WebSocket──> Data Collection
└─────────────────┘                      │
                                         ▼
┌─────────────────┐              ┌──────────────┐
│   Routinator    │ <──RPKI──    │  PostgreSQL  │
│  (Docker)       │    Check     │   Database   │
└─────────────────┘              └──────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
            ┌───────────────┐    ┌─────────────┐    ┌──────────────┐
            │Feature Extract│    │  Heuristic  │    │  ML Inference│
            │  Aggregator   │    │  Detector   │    │   Service    │
            └───────────────┘    └─────────────┘    └──────────────┘
                    │                    │                    │
                    └────────────────────┼────────────────────┘
                                         ▼
                                ┌─────────────────┐
                                │ Correlation     │
                                │ Engine          │
                                └─────────────────┘
                                         │
                                         ▼
                                ┌─────────────────┐
                                │  Dashboard API  │
                                │  (Flask+Socket) │
                                └─────────────────┘
                                         │
                                         ▼
                                ┌─────────────────┐
                                │  React Frontend │
                                │  (Port 3000)    │
                                └─────────────────┘
```

## ✅ Prerequisites

### Required Software

1. **Python 3.11+**
   - Download: https://www.python.org/downloads/
   - **Important:** During installation, check "Add Python to PATH"

2. **PostgreSQL 16**
   - Download: https://www.postgresql.org/download/
   - Default port: 5432
   - Remember your postgres password during installation

3. **Docker Desktop** (for Routinator RPKI validator)
   - Download: https://www.docker.com/products/docker-desktop/

4. **Node.js 18+** (for React dashboard)
   - Download: https://nodejs.org/
   - LTS version recommended

## 📥 Installation

### 1. Clone the Repository

### 2. Database Setup

#### Create PostgreSQL Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE bgp_ensemble_db;

# Exit psql
\q
```

#### Initialize Database Schema

```bash
# Run schema creation script (if you have one)
psql -U postgres -d bgp_ensemble_db -f schema.sql
```

**Note:** The main.py service will create tables automatically on first run.

### 3. Python Environment Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Windows CMD:
.venv\Scripts\activate.bat

# Linux/Mac:
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 4. Routinator (RPKI Validator) Setup

```bash
# Pull Routinator Docker image
docker pull nlnetlabs/routinator

# Start Routinator container
docker run -d --name routinator \
  -p 3323:3323 \
  -p 8323:8323 \
  nlnetlabs/routinator
```

**Verify Routinator is running:**
```bash
curl http://localhost:8323/api/v1/status
```

### 5. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install Node.js dependencies
npm install

# Build production version
npm run build

# Return to project root
cd ..
```

## ⚙️ Configuration

### Database Connection

Edit database connection settings in each Python service file:

**File locations:**
- `main.py` (line ~30)
- `feature_aggregator.py` (line ~20)
- `heuristic_detector.py` (line ~20)
- `ml_inference_service.py` (line ~25)
- `correlation_engine.py` (line ~20)
- `rpki_validator_service.py` (line ~20)
- `dashboard_api.py` (line ~30)

**Example configuration:**
```python
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'bgp_ensemble_db',
    'user': 'postgres',
    'password': 'your_password_here'  #
}
```

### Environment Variables (Optional)

Create `.env` file in project root:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=bgp_ensemble_db
DB_USER=postgres
DB_PASSWORD=your_password_here
ROUTINATOR_URL=http://localhost:8323
```

## 🚀 Running the System

### Option 1: Automated Startup (Windows PowerShell)

```powershell
.\start_all.ps1
```

This script will:
1. ✅ Check and start PostgreSQL service
2. ✅ Start Routinator Docker container
3. ✅ Launch all 8 Python services
4. ✅ Start React frontend server

### Option 2: Manual Startup

**Terminal 1 - Data Collection:**
```bash
python main.py
```

**Terminal 2 - Feature Aggregation:**
```bash
python feature_aggregator.py
```

**Terminal 3 - Heuristic Detection:**
```bash
python heuristic_detector.py
```

**Terminal 4 - ML Inference:**
```bash
python ml_inference_service.py
```

**Terminal 5 - Correlation Engine:**
```bash
python correlation_engine.py
```

**Terminal 6 - RPKI Validator:**
```bash
python rpki_validator_service.py
```

**Terminal 7 - Dashboard API:**
```bash
python dashboard_api.py
```

**Terminal 8 - Frontend:**
```bash
cd frontend
npm start
```

### Verify Services are Running

```powershell
# Check Python processes
Get-Process python

# Check Node.js processes
Get-Process node

# Check Routinator
docker ps | Select-String "routinator"
```

You should see:
- **8 Python processes** (main.py + 7 services)
- **2 Node.js processes** (React dev server)
- **1 Routinator container** (running)

## 🌐 Dashboard Access

Once all services are running:

**Main Dashboard:** http://localhost:3000

### Dashboard Features

- **Active Anomalies Widget** - Real-time anomaly alerts
- **Statistics Overview** - Total routes, BGP peers, anomalies
- **RPKI Summary** - Validation statistics
- **Recent Updates** - Latest BGP messages
- **Top Prefixes** - Most active IP prefixes
- **Top ASNs** - Most active Autonomous Systems
- **Advanced Analytics** - Correlation matrices and trends
- **Historical Playback** - Time-travel through BGP events

## 📁 Project Structure

```
bgp-monitoring-system/
├── main.py                          # Data collection from RIPE RIS
├── feature_aggregator.py            # Feature extraction (1-min, 5-min windows)
├── heuristic_detector.py            # Rule-based anomaly detection
├── ml_inference_service.py          # LSTM + Isolation Forest inference
├── correlation_engine.py            # Anomaly correlation and scoring
├── rpki_validator_service.py        # RPKI route validation
├── dashboard_api.py                 # REST API + WebSocket server
├── cleanup_old_data.py              # Database maintenance
├── start_all.ps1                    # Automated startup script
├── requirements.txt                 # Python dependencies
├── .gitignore                       # Git ignore rules
├── README.md                        # This file
│
├── frontend/                        # React dashboard
│   ├── src/
│   │   ├── components/              # React components
│   │   │   ├── widgets/             # Dashboard widgets
│   │   │   └── App.jsx              # Main app
│   │   └── index.js
│   ├── public/
│   ├── package.json
│   └── README.md
│
├── archive_old_scripts/             # Historical scripts (not in git)
│   └── backup_1min_windows_2026-01-07_1252/
│
└── __pycache__/                     # Python cache (not in git)
```

## 📡 API Documentation

### REST Endpoints

**Base URL:** `http://localhost:5000`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stats` | GET | System statistics |
| `/api/anomalies/recent` | GET | Recent anomalies (last 24h) |
| `/api/anomalies/active` | GET | Currently active anomalies |
| `/api/updates/recent` | GET | Recent BGP updates |
| `/api/prefixes/top` | GET | Top active prefixes |
| `/api/asns/top` | GET | Top active ASNs |
| `/api/rpki/summary` | GET | RPKI validation summary |
| `/api/analytics/correlations` | GET | Anomaly correlation matrix |
| `/api/historical` | GET | Historical data for playback |

### WebSocket Events

**Connect:** `ws://localhost:5000`

**Client → Server:**
```javascript
socket.emit('subscribe_anomalies');
```

**Server → Client:**
```javascript
socket.on('anomaly', (data) => {
  // Real-time anomaly alert
  console.log(data);
});
```

## 🔧 Troubleshooting

### PostgreSQL Connection Failed

**Error:** `psycopg2.OperationalError: connection failed`

**Solution:**
1. Check PostgreSQL is running:
   ```powershell
   Get-Service postgresql*
   ```
2. Start if stopped:
   ```powershell
   Start-Service postgresql-x64-16
   ```
3. Verify password in DB_CONFIG

### Routinator Not Responding

**Error:** `Connection refused to localhost:8323`

**Solution:**
```bash
# Check Routinator status
docker ps -a | Select-String "routinator"

# Restart Routinator
docker restart routinator

# View logs
docker logs routinator
```

### No Data from RIPE RIS

**Error:** Services running but no BGP data appearing

**Solution:**
1. Check main.py logs for WebSocket connection
2. Verify internet connectivity
3. RIPE RIS Live URL: `wss://ris-live.ripe.net/v1/ws/`
4. Check if RIS is operational: https://ris-live.ripe.net/

### ML Model Errors

**Note:** Pre-trained models included in `models/` directory

**Solution:**
Pre-trained ML models are included! The system is ready to detect anomalies immediately:
  1. Models are located in `models/` directory
  2. LSTM model, Isolation Forest, and scalers included
  3. No initial training required - works out of the box
  4. Optional: Retrain models using your data (see `models/README.md`)

### Frontend Build Failed

**Error:** `npm install` or `npm start` fails

**Solution:**
```bash
cd frontend

# Clear cache
npm cache clean --force

# Delete node_modules
rm -rf node_modules package-lock.json

# Reinstall
npm install

# Rebuild
npm run build
```

### Port Already in Use

**Error:** `Port 5000 already in use`

**Solution:**
```powershell
# Find process using port 5000
netstat -ano | findstr :5000

# Kill process (replace PID)
Stop-Process -Id <PID> -Force
```

## 📊 Data Flow

1. **RIPE RIS Live** → `main.py` → Inserts to `ip_rib`, `ris_message_log`
2. **feature_aggregator.py** → Reads `ip_rib` → Writes `aggregated_features_1min`, `aggregated_features_5min`
3. **heuristic_detector.py** → Reads features → Writes `heuristic_anomalies`
4. **ml_inference_service.py** → Reads features → Writes `ml_anomalies`
5. **rpki_validator_service.py** → Reads `ip_rib` → Validates via Routinator → Writes `rpki_validation`
6. **correlation_engine.py** → Reads all anomalies → Writes `detected_anomalies`
7. **dashboard_api.py** → Serves data to React frontend
8. **cleanup_old_data.py** → Maintains database (deletes data >30 days)


## 📝 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- **RIPE NCC** - RIS Live BGP data feed
- **NLnet Labs** - Routinator RPKI validator
- **TensorFlow** - Machine learning framework
- **React** - Frontend framework

---

**Made with ❤️ for Internet Security**
