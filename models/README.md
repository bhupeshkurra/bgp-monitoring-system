# ML Models Directory

This directory contains the trained machine learning models for anomaly detection.

## Required Model Files

The BGP Monitoring System uses the following ML models:

1. **lstm_model.h5** - LSTM neural network for sequence-based anomaly detection
2. **isolation_forest.pkl** - Isolation Forest for outlier detection  
3. **scaler.pkl** - Feature scaler (StandardScaler) for data normalization

## Model Training

Since ML models require training data, you have two options:

### Option 1: Use Pre-trained Models (Recommended for Quick Start)

If you have pre-trained models, place them in this directory:
```
models/
   lstm_model.h5
   isolation_forest.pkl
   scaler.pkl
```

### Option 2: Train Models from Scratch

The system will automatically train models when it collects enough data:

1. **Start the system** without models (it will use heuristic detection only)
2. **Let it run for 24-48 hours** to collect training data in `bgp_features_1min` table
3. **Run the training script** (coming soon) or train manually:

```python
# Example training script structure
import pandas as pd
import numpy as np
from tensorflow import keras
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import psycopg2
import joblib

# 1. Fetch training data from database
conn = psycopg2.connect(
    host="localhost",
    database="bgp_ensemble_db",
    user="postgres",
    password="your_password"
)

query = """
    SELECT 
        announcements, withdrawals, total_updates,
        withdrawal_ratio, flap_count, path_length,
        unique_peers, message_rate, session_resets
    FROM bgp_features_1min
    WHERE window_start >= NOW() - INTERVAL '7 days'
    ORDER BY window_start
"""

df = pd.read_sql(query, conn)
conn.close()

# 2. Prepare features
features = [
    'announcements', 'withdrawals', 'total_updates',
    'withdrawal_ratio', 'flap_count', 'path_length',
    'unique_peers', 'message_rate', 'session_resets'
]

X = df[features].fillna(0).values

# 3. Train scaler
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Save scaler
joblib.dump(scaler, 'models/scaler.pkl')
print(" Scaler saved")

# 4. Train Isolation Forest
iso_forest = IsolationForest(
    contamination=0.1,
    random_state=42,
    n_estimators=100
)
iso_forest.fit(X_scaled)

# Save Isolation Forest
joblib.dump(iso_forest, 'models/isolation_forest.pkl')
print(" Isolation Forest saved")

# 5. Train LSTM
# Reshape for LSTM (samples, timesteps, features)
timesteps = 10
X_lstm = []
for i in range(len(X_scaled) - timesteps):
    X_lstm.append(X_scaled[i:i+timesteps])
X_lstm = np.array(X_lstm)

# Create LSTM model
model = keras.Sequential([
    keras.layers.LSTM(64, input_shape=(timesteps, len(features)), return_sequences=True),
    keras.layers.Dropout(0.2),
    keras.layers.LSTM(32),
    keras.layers.Dropout(0.2),
    keras.layers.Dense(16, activation='relu'),
    keras.layers.Dense(len(features))
])

model.compile(optimizer='adam', loss='mse')

# Train (using autoencoder approach)
model.fit(
    X_lstm, X_scaled[timesteps:],
    epochs=50,
    batch_size=32,
    validation_split=0.2,
    verbose=1
)

# Save LSTM
model.save('models/lstm_model.h5')
print(" LSTM model saved")
```

## Model Specifications

### LSTM Model
- **Input shape**: (10, 9) - 10 timesteps, 9 features
- **Architecture**: 2 LSTM layers (64, 32 units) + 2 Dense layers
- **Loss function**: MSE (Mean Squared Error)
- **Purpose**: Sequence anomaly detection using reconstruction error

### Isolation Forest
- **Contamination**: 0.1 (10% expected anomalies)
- **Estimators**: 100 trees
- **Purpose**: Outlier detection for point anomalies

### Feature Scaler
- **Type**: StandardScaler
- **Features**: 9 BGP metrics (announcements, withdrawals, etc.)
- **Purpose**: Normalize features to mean=0, std=1

## Running Without Models

The system gracefully handles missing models:
- **ML Inference Service** will log warnings but continue
- **Heuristic Detection** remains fully operational
- **RPKI Validation** remains fully operational
- Only ML-based detections will be unavailable

## Notes

- Models should be retrained periodically (e.g., monthly) to adapt to network changes
- Training requires at least 7 days of normal BGP data for good results
- Larger datasets (30+ days) produce more robust models
