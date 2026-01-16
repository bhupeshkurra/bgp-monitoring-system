# Quick Setup Guide - BGP Monitoring System

**Estimated Setup Time:** 30-45 minutes

## 🎯 Step-by-Step Installation

### Step 1: Install PostgreSQL (10 minutes)

1. Download PostgreSQL 16: https://www.postgresql.org/download/windows/
2. Run installer
3. **Important settings:**
   - Port: `5432` (default)
   - Password: Choose a strong password (remember this!)
   - Locale: English, United States
4. Finish installation
5. Verify installation:
   ```powershell
   psql --version
   ```

**Create Database:**
```powershell
# Open PowerShell as Administrator
$env:PGPASSWORD='your_password_here'
psql -U postgres -c "CREATE DATABASE bgp_ensemble_db;"
```

---

### Step 2: Install Docker Desktop (5 minutes)

1. Download: https://www.docker.com/products/docker-desktop/
2. Run installer
3. Restart computer if prompted
4. Open Docker Desktop
5. Wait for "Docker is running" message

**Start Routinator:**
```powershell
docker run -d --name routinator -p 3323:3323 -p 8323:8323 nlnetlabs/routinator
```

**Verify:**
```powershell
docker ps
# Should show routinator container running
```

---

### Step 3: Install Python 3.11+ (5 minutes)

1. Download: https://www.python.org/downloads/
2. Run installer
3. ✅ **IMPORTANT:** Check "Add Python to PATH"
4. Click "Install Now"
5. Verify installation:
   ```powershell
   python --version
   # Should show Python 3.11 or higher
   ```

---

### Step 4: Install Node.js (5 minutes)

1. Download LTS version: https://nodejs.org/
2. Run installer
3. Accept all defaults
4. Verify installation:
   ```powershell
   node --version
   npm --version
   ```

---

### Step 5: Clone & Setup Project (10 minutes)

```powershell
# Navigate to your projects folder
cd E:\projects  # or wherever you want

# Clone repository
git clone https://github.com/yourusername/bgp-monitoring-system.git
cd bgp-monitoring-system

# Create Python virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install Python dependencies
pip install -r requirements.txt
```

---

### Step 6: Configure Database Password (2 minutes)

Edit the following files and replace `'your_password_here'` with your actual PostgreSQL password:

**Files to edit:**
- [ ] `main.py` (line ~30)
- [ ] `feature_aggregator.py` (line ~20)
- [ ] `heuristic_detector.py` (line ~20)
- [ ] `ml_inference_service.py` (line ~25)
- [ ] `correlation_engine.py` (line ~20)
- [ ] `rpki_validator_service.py` (line ~20)
- [ ] `dashboard_api.py` (line ~30)
- [ ] `cleanup_old_data.py` (line ~15)

**Find this block:**
```python
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'bgp_ensemble_db',
    'user': 'postgres',
    'password': 'your_password_here'  # ⚠️ CHANGE THIS!
}
```

**Replace with:**
```python
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'bgp_ensemble_db',
    'user': 'postgres',
    'password': 'jia091004'  # Your actual password
}
```

---

### Step 7: Setup Frontend (5 minutes)

```powershell
cd frontend
npm install
cd ..
```

---

### Step 8: Start the System (2 minutes)

```powershell
# Run startup script
.\start_all.ps1
```

**The script will automatically:**
1. ✅ Check PostgreSQL is running
2. ✅ Start Routinator Docker container
3. ✅ Launch 8 Python services
4. ✅ Start React frontend

---

### Step 9: Access Dashboard

Open your browser and go to:
**http://localhost:3000**

You should see the BGP Monitoring Dashboard!

---

## ✅ Verification Checklist

After setup, verify everything is running:

```powershell
# Check Python processes (should see 8)
Get-Process python | Measure-Object

# Check Node processes (should see 2)
Get-Process node | Measure-Object

# Check Routinator
docker ps | Select-String "routinator"

# Check PostgreSQL
Get-Service postgresql*
```

**Expected results:**
- ✅ 8 Python processes
- ✅ 2 Node.js processes
- ✅ 1 Routinator container (status: Up)
- ✅ PostgreSQL service (status: Running)

---

## 🚨 Common Issues & Quick Fixes

### PostgreSQL Service Not Running

```powershell
Start-Service postgresql-x64-16
```

### Routinator Container Stopped

```powershell
docker start routinator
```

### Port 3000 Already in Use

```powershell
# Find process
netstat -ano | findstr :3000

# Kill process (replace 12345 with actual PID)
Stop-Process -Id 12345 -Force
```

### Virtual Environment Not Activating

```powershell
# If PowerShell execution policy error:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then try again:
.\.venv\Scripts\Activate.ps1
```

---

## 📊 Expected Behavior After Startup

### First 5 Minutes:
- Services connect to database
- Tables are created automatically
- RIPE RIS Live connection established
- BGP data starts flowing

### After 10 Minutes:
- Dashboard shows BGP peers: ~500+
- Total routes: ~50,000+
- Recent updates appearing

### After 1 Hour:
- Feature aggregation running
- Heuristic detection active
- ML models training

### After 2 Hours:
- ML anomaly detection active
- Correlation engine running
- Full system operational

---

## 🎓 Next Steps

Once the system is running:

1. **Explore Dashboard:**
   - Monitor active anomalies
   - Check RPKI validation
   - View top prefixes and ASNs

2. **Read Documentation:**
   - API endpoints: See README.md
   - System architecture
   - Data flow diagrams

3. **Customize Settings:**
   - Adjust detection thresholds
   - Configure alert rules
   - Set up notifications

---

## 🛑 Stopping the System

```powershell
# Stop all Python processes
Get-Process python,node -ErrorAction SilentlyContinue | Stop-Process -Force

# Stop Routinator
docker stop routinator

# Stop PostgreSQL (optional)
Stop-Service postgresql-x64-16
```

---

## 💡 Tips for Smooth Operation

1. **Always activate virtual environment** before running Python scripts
2. **PostgreSQL must be running** before starting services
3. **Routinator must be started** before RPKI validation works
4. **Wait 2-3 minutes** between stopping and restarting services
5. **Check logs** if something isn't working (each service prints status)

---

**Need Help?** Check the Troubleshooting section in README.md or open an issue on GitHub!
