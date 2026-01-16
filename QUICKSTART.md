# Quick Start Guide

Get the BGP Monitoring System running in **15 minutes** (without ML models) or **30 minutes** (full setup).

## Prerequisites Checklist

- [ ] PostgreSQL 13+ installed
- [ ] Python 3.11+ installed  
- [ ] Docker Desktop installed (for Routinator)
- [ ] Node.js 18+ installed (for React dashboard)
- [ ] Git installed

## Step-by-Step Setup

### 1. Clone and Navigate (1 min)

```bash
git clone https://github.com/YOUR_USERNAME/bgp-monitoring-system.git
cd bgp-monitoring-system
```

### 2. Configure Environment (2 min)

```bash
# Copy environment template
cp .env.example .env

# Edit .env and set your PostgreSQL password
# On Windows: notepad .env
# On Linux/Mac: nano .env
```

**Update this line in `.env`:**
```env
DB_PASSWORD=your_actual_postgres_password
```

### 3. Install Python Dependencies (3 min)

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 4. Setup Database (2 min)

```bash
python setup_database.py
```

This will:
- Create `bgp_ensemble_db` database
- Create all required tables
- Initialize state tracking
- Verify setup

### 5. Start Routinator (RPKI Validator) (3 min)

```bash
# Pull and run Routinator in Docker
docker run -d --name routinator \
  -p 9556:9556 \
  nlnetlabs/routinator:latest \
  routinator server --http 0.0.0.0:9556

# Verify it's running (should return JSON)
curl http://localhost:9556/api/v1/status
```

**Windows PowerShell:**
```powershell
docker run -d --name routinator -p 9556:9556 nlnetlabs/routinator:latest routinator server --http 0.0.0.0:9556
Invoke-WebRequest http://localhost:9556/api/v1/status
```

### 6. Start Backend Services (1 min)

```bash
# All services in one command
python main.py
```

This starts:
- BGP data collector (RIPE RIS Live)
- Feature aggregator
- Heuristic detector
- ML inference (if models available)
- RPKI validator service
- Correlation engine

### 7. Setup React Dashboard (3 min)

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Dashboard will be available at: **http://localhost:5173**

### 8. Verify Everything Works 

Open your browser:
- **Dashboard**: http://localhost:5173
- **API Health**: http://localhost:5000/api/health
- **Routinator**: http://localhost:9556/api/v1/status

You should see:
-  Live BGP routes appearing in dashboard
-  Feature aggregation running every minute
-  Real-time updates via WebSocket
-  RPKI validation status

---

## Quick Start (Without Frontend)

If you only want the backend detection system:

```bash
# Steps 1-5 (clone, env, dependencies, database, routinator)
# Then:
python main.py
```

Access via API: http://localhost:5000/api/detections

---

## Troubleshooting

### Database Connection Fails
```bash
# Check PostgreSQL is running
# Windows:
Get-Service postgresql*
# Linux:
sudo systemctl status postgresql
```

### Routinator Not Starting
```bash
# Check if port 9556 is in use
# Windows:
netstat -ano | findstr :9556
# Linux:
sudo lsof -i :9556

# Stop and remove existing container
docker stop routinator
docker rm routinator
```

### No BGP Data Appearing
```bash
# Check RIS Live connection in logs
# Look for "Connected to RIPE RIS Live" message
# Data starts flowing within 1-2 minutes
```

### ML Models Missing
```
  This is expected on first run!
```
System works fine without ML models:
- Heuristic detection:  Active
- RPKI validation:  Active  
- ML detection:  Disabled (train models after 24-48 hours of data collection)

See `models/README.md` for training instructions.

---

## Production Deployment

For production use:

```bash
# Use production build for frontend
cd frontend
npm run build

# Serve build folder with nginx/apache
# Or use: python -m http.server 8080 -d dist

# Run backend as systemd service (Linux) or Windows Service
# See SETUP_GUIDE.md for details
```

---

## What's Next?

1. **Monitor Dashboard**: Watch live BGP updates and anomaly detections
2. **Collect Data**: Let system run 24-48 hours to gather training data
3. **Train ML Models**: Follow `models/README.md` to train LSTM and Isolation Forest
4. **Configure Alerts**: Customize detection thresholds in `.env`
5. **Scale Up**: Add more BGP peers, enable historical playback

---

## Need Help?

-  Full documentation: See `README.md` and `SETUP_GUIDE.md`
-  Issues: Open a GitHub issue
-  Questions: Check troubleshooting section

**System is ready! Happy BGP monitoring! **
