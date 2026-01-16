#!/usr/bin/env python3
"""
ML Inference Service for BGP Anomaly Detection

Continuously monitors bgp_features_5min table, runs LSTM + Isolation Forest models,
computes z-score ensemble, and writes detections to hybrid_anomaly_detections.
"""

from __future__ import annotations

import os
import sys
import time
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass

import numpy as np
import pandas as pd
import psycopg
from psycopg import Connection
import joblib
from tensorflow import keras

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Configuration
ENSEMBLE_METHOD = os.getenv("ENSEMBLE_METHOD", "avg")  # "avg" or "max"
ANOMALY_THRESHOLD = float(os.getenv("ANOMALY_THRESHOLD", "3.0"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))  # seconds (faster for 1-min windows)
LSTM_SEQUENCE_LENGTH = int(os.getenv("LSTM_SEQUENCE_LENGTH", "10"))
MODEL_VERSION = "v1.0"

# Feature columns (must match training order)
FEATURE_COLUMNS = [
    "announcements",
    "withdrawals",
    "total_updates",
    "withdrawal_ratio",
    "flap_count",
    "path_length",
    "unique_peers",
    "message_rate",
    "session_resets"
]


@dataclass
class ModelArtifacts:
    """Container for loaded ML models and scalers."""
    isolation_forest: Any
    feature_scaler: Any
    lstm_model: Any
    lstm_scaler: Optional[Any]
    baseline_stats: Dict[str, Dict[str, float]]


def build_dsn() -> str:
    """Build PostgreSQL DSN from environment variables."""
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "bgp_ensemble_db")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "your_password_here")
    
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def get_db_connection() -> Connection:
    """
    Create database connection with autocommit mode.
    
    Returns:
        Active psycopg Connection
    """
    dsn = build_dsn()
    conn = psycopg.connect(dsn, autocommit=True)
    return conn


def init_state_table(conn: Connection) -> None:
    """
    Create ml_inference_state table if it doesn't exist.
    
    Args:
        conn: Database connection
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ml_inference_state (
                id INTEGER PRIMARY KEY DEFAULT 1,
                last_processed_timestamp TIMESTAMP WITHOUT TIME ZONE,
                total_processed BIGINT DEFAULT 0,
                last_update TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                CHECK (id = 1)
            )
        """)
        
        # Insert initial row if doesn't exist
        cur.execute("""
            INSERT INTO ml_inference_state (id, last_processed_timestamp, total_processed)
            VALUES (1, '1970-01-01'::timestamp, 0)
            ON CONFLICT (id) DO NOTHING
        """)
    
    logger.info("Initialized ml_inference_state table")


def get_last_processed_timestamp(conn: Connection) -> datetime:
    """
    Get the last processed timestamp from state table.
    
    Args:
        conn: Database connection
        
    Returns:
        Last processed timestamp
    """
    with conn.cursor() as cur:
        cur.execute("SELECT last_processed_timestamp FROM ml_inference_state WHERE id = 1")
        result = cur.fetchone()
        if result:
            return result[0]
        return datetime(1970, 1, 1)


def update_state(conn: Connection, last_ts: datetime, processed_count: int) -> None:
    """
    Update the last processed timestamp and count.
    
    Args:
        conn: Database connection
        last_ts: Timestamp of last processed row
        processed_count: Number of rows processed in this batch
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE ml_inference_state
            SET last_processed_timestamp = %s,
                total_processed = total_processed + %s,
                last_update = NOW()
            WHERE id = 1
        """, (last_ts, processed_count))


def load_models_and_baseline() -> ModelArtifacts:
    """
    Load trained ML models, scalers, and baseline statistics.
    
    Returns:
        ModelArtifacts container with all loaded artifacts
        
    Raises:
        FileNotFoundError: If model files are missing
    """
    logger.info("Loading ML models and artifacts...")
    
    # Model directory
    model_dir = os.path.join(".venv", "Scripts", "updated models")
    
    # Load Isolation Forest and scaler
    try:
        isolation_forest = joblib.load(os.path.join(model_dir, "isolation_forest_model.pkl"))
        feature_scaler = joblib.load(os.path.join(model_dir, "feature_scaler.pkl"))
        logger.info("[OK] Loaded Isolation Forest model and scaler")
    except FileNotFoundError as e:
        logger.error(f"Failed to load Isolation Forest artifacts: {e}")
        raise
    
    # Load LSTM model with custom objects for compatibility
    try:
        # Handle Keras version compatibility issues
        custom_objects = {
            'mse': keras.losses.MeanSquaredError(),
            'mae': keras.losses.MeanAbsoluteError()
        }
        lstm_model = keras.models.load_model(
            os.path.join(model_dir, "lstm_model.h5"),
            custom_objects=custom_objects,
            compile=False
        )
        # Recompile with current Keras version
        lstm_model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        logger.info("[OK] Loaded LSTM model")
    except Exception as e:
        logger.error(f"Failed to load LSTM model: {e}")
        raise
    
    # Try to load LSTM scaler (optional)
    lstm_scaler = None
    try:
        lstm_scaler = joblib.load(os.path.join(model_dir, "lstm_scaler.pkl"))
        logger.info("[OK] Loaded LSTM scaler")
    except FileNotFoundError:
        logger.warning("LSTM scaler not found, will use feature_scaler")
        lstm_scaler = feature_scaler
    
    # Load or compute baseline statistics for z-score normalization
    # Updated with actual statistics computed from real model outputs
    baseline_stats = {
        "isolation_forest": {
            "mean": -0.14,  # Computed from existing detections
            "std": 0.012    # Actual variation in decision scores
        },
        "lstm": {
            "mean": 13.99,  # Actual MSE mean from model outputs
            "std": 2.68     # Actual MSE std dev
        }
    }
    
    logger.info("[OK] Loaded baseline statistics for z-score normalization")
    
    return ModelArtifacts(
        isolation_forest=isolation_forest,
        feature_scaler=feature_scaler,
        lstm_model=lstm_model,
        lstm_scaler=lstm_scaler,
        baseline_stats=baseline_stats
    )


def fetch_new_feature_rows(conn: Connection, last_ts: datetime) -> pd.DataFrame:
    """
    Fetch new rows from bgp_features_1min since the last processed timestamp.
    
    Args:
        conn: Database connection
        last_ts: Last processed timestamp
        
    Returns:
        DataFrame with new feature rows
    """
    query = f"""
        SELECT 
            window_start,
            prefix,
            origin_as,
            announcements,
            withdrawals,
            total_updates,
            withdrawal_ratio,
            flap_count,
            path_length,
            unique_peers,
            message_rate,
            session_resets
        FROM bgp_features_1min
        WHERE window_start > %s
        ORDER BY window_start, prefix, origin_as
    """
    
    df = pd.read_sql(query, conn, params=(last_ts,))
    
    if len(df) > 0:
        logger.info(f"Fetched {len(df)} new feature rows since {last_ts}")
    
    return df


def compute_iso_scores(df: pd.DataFrame, models: ModelArtifacts) -> np.ndarray:
    """
    Compute Isolation Forest anomaly scores.
    
    Args:
        df: DataFrame with feature columns
        models: Loaded model artifacts
        
    Returns:
        Array of anomaly scores (lower = more anomalous)
    """
    if len(df) == 0:
        return np.array([])
    
    # Extract feature matrix in correct order
    X = df[FEATURE_COLUMNS].values
    
    # Handle missing values
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    
    # Scale features
    X_scaled = models.feature_scaler.transform(X)
    
    # Compute anomaly scores (decision_function returns negative for anomalies)
    scores = models.isolation_forest.decision_function(X_scaled)
    
    return scores


def compute_lstm_scores(df: pd.DataFrame, models: ModelArtifacts) -> Dict[Tuple, float]:
    """
    Compute LSTM anomaly scores using sequence-based reconstruction error.
    
    Groups data by (prefix, origin_as) and creates sequences for LSTM prediction.
    For large batches (backfill), uses sampling to avoid excessive processing time.
    
    Args:
        df: DataFrame with feature columns and time ordering
        models: Loaded model artifacts
        
    Returns:
        Dictionary mapping (prefix, origin_as, window_start) -> anomaly_score
    """
    if len(df) == 0:
        return {}
    
    scores_dict = {}
    
    # Convert prefix to string to avoid IPv4/IPv6 comparison issues
    df = df.copy()
    df['prefix'] = df['prefix'].astype(str)
    
    # For large backfills, sample to avoid excessive processing time
    # Process at most 5000 groups, sample the rest
    unique_groups = df.groupby(['prefix', 'origin_as']).ngroups
    
    if unique_groups > 5000:
        logger.warning(f"LSTM: Processing {unique_groups} groups would take too long. Sampling 5000 groups and using mean score for others.")
        # Sample groups
        all_groups = df.groupby(['prefix', 'origin_as'])
        group_keys = list(all_groups.groups.keys())
        import random
        random.seed(42)
        sampled_keys = random.sample(group_keys, min(5000, len(group_keys)))
        sampled_groups = {k: all_groups.get_group(k) for k in sampled_keys}
        process_sample = True
    else:
        sampled_groups = df.groupby(['prefix', 'origin_as'])
        process_sample = False
    
    # Process sampled or all groups
    processed_scores = []
    group_count = 0
    
    iterator = sampled_groups.items() if process_sample else df.groupby(['prefix', 'origin_as'])
    
    for (prefix, origin_as), group in iterator:
        group_count += 1
        if group_count % 500 == 0:
            logger.info(f"LSTM: Processed {group_count}/{len(sampled_groups) if process_sample else unique_groups} groups...")
        
        # Sort by time
        group = group.sort_values('window_start')
        
        # Extract features
        X = group[FEATURE_COLUMNS].values
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        
        # Scale - use feature_scaler for consistency (lstm_scaler may have distribution mismatch)
        X_scaled = models.feature_scaler.transform(X)
        
        # Create sequences of fixed length
        seq_len = LSTM_SEQUENCE_LENGTH
        
        if len(X_scaled) < seq_len:
            # Not enough data for sequence, use mean padding
            padded = np.zeros((seq_len, X_scaled.shape[1]))
            padded[:len(X_scaled)] = X_scaled
            X_scaled = padded
        
        # For each window in the group, create a sequence ending at that window
        for i in range(len(group)):
            window_start = group.iloc[i]['window_start']
            
            # Get sequence ending at current window
            start_idx = max(0, i - seq_len + 1)
            end_idx = i + 1
            
            sequence = X_scaled[start_idx:end_idx]
            
            # Pad if necessary
            if len(sequence) < seq_len:
                padded = np.zeros((seq_len, sequence.shape[1]))
                padded[-len(sequence):] = sequence
                sequence = padded
            
            # Reshape for LSTM: (1, seq_len, features)
            X_seq = sequence.reshape(1, seq_len, -1)
            
            try:
                # Predict (reconstruction or forecast depending on model type)
                prediction = models.lstm_model.predict(X_seq, verbose=0)
                
                # Compute reconstruction error (MSE)
                actual = sequence[-1]  # Last timestep
                if prediction.shape[1] == len(actual):
                    pred_last = prediction[0]
                else:
                    # If model outputs sequences, take last timestep
                    pred_last = prediction[0, -1, :]
                
                mse = np.mean((actual - pred_last) ** 2)
                
                # Store score with consistent key types
                key = (str(prefix), int(origin_as), pd.Timestamp(window_start))
                scores_dict[key] = float(mse)
                processed_scores.append(float(mse))
                
            except Exception as e:
                logger.warning(f"LSTM prediction failed for {prefix}, {origin_as}: {e}")
                key = (str(prefix), int(origin_as), pd.Timestamp(window_start))
                scores_dict[key] = 0.0
    
    # For unprocessed rows (when sampling), use mean of processed scores
    if process_sample and len(processed_scores) > 0:
        mean_score = np.mean(processed_scores)
        logger.info(f"LSTM: Using mean score {mean_score:.6f} for {len(df) - len(scores_dict)} unprocessed rows")
        logger.info(f"DEBUG: processed_scores sample: {processed_scores[:10]}")
        for _, row in df.iterrows():
            key = (str(row['prefix']), int(row['origin_as']), pd.Timestamp(row['window_start']))
            if key not in scores_dict:
                scores_dict[key] = mean_score
    
    logger.info(f"LSTM: Completed scoring {len(scores_dict)} rows")
    logger.info(f"DEBUG: scores_dict sample (first 5): {list(scores_dict.items())[:5]}")
    return scores_dict


def compute_z_score_ensemble(
    iso_scores: np.ndarray,
    lstm_scores_dict: Dict[Tuple, float],
    df: pd.DataFrame,
    models: ModelArtifacts
) -> pd.DataFrame:
    """
    Compute z-score normalized ensemble scores.
    
    Args:
        iso_scores: Isolation Forest anomaly scores
        lstm_scores_dict: LSTM scores keyed by (prefix, origin_as, window_start)
        df: Original feature DataFrame
        models: Model artifacts with baseline statistics
        
    Returns:
        DataFrame with columns: z_iso, z_lstm, combined_score, combined_anomaly, combined_severity
    """
    results = []
    
    baseline = models.baseline_stats
    iso_mean = baseline["isolation_forest"]["mean"]
    iso_std = baseline["isolation_forest"]["std"]
    lstm_mean = baseline["lstm"]["mean"]
    lstm_std = baseline["lstm"]["std"]
    
    # Debug: log first few lookups
    debug_count = 0
    
    for i, row in df.iterrows():
        # Get raw scores
        iso_raw = iso_scores[i] if i < len(iso_scores) else 0.0
        
        # Use consistent key format for lookup
        key = (str(row['prefix']), int(row['origin_as']), pd.Timestamp(row['window_start']))
        lstm_raw = lstm_scores_dict.get(key, 0.0)
        
        # Debug first few lookups
        if debug_count < 3:
            logger.info(f"DEBUG z-score: key={key}, lstm_raw={lstm_raw:.6f}, key_in_dict={key in lstm_scores_dict}")
            if key not in lstm_scores_dict and len(lstm_scores_dict) > 0:
                sample_keys = list(lstm_scores_dict.keys())[:3]
                logger.info(f"  Sample dict keys: {sample_keys}")
            debug_count += 1
        
        # Compute z-scores
        z_iso = (iso_raw - iso_mean) / iso_std if iso_std > 0 else 0.0
        z_lstm = (lstm_raw - lstm_mean) / lstm_std if lstm_std > 0 else 0.0
        
        # For Isolation Forest: negative scores are anomalies, so flip sign
        z_iso = -z_iso
        
        # Ensemble: average or max
        if ENSEMBLE_METHOD == "max":
            combined = max(z_iso, z_lstm)
        else:  # avg
            combined = (z_iso + z_lstm) / 2.0
        
        # Determine anomaly and severity
        is_anomaly = combined >= ANOMALY_THRESHOLD
        
        if combined < 2.0:
            severity = "low"
        elif combined < 3.0:
            severity = "low"
        elif combined < 4.0:
            severity = "medium"
        elif combined < 5.0:
            severity = "high"
        else:
            severity = "critical"
        
        results.append({
            "iso_raw": iso_raw,
            "lstm_raw": lstm_raw,
            "z_iso": z_iso,
            "z_lstm": z_lstm,
            "combined_score": combined,
            "combined_anomaly": is_anomaly,
            "combined_severity": severity
        })
    
    return pd.DataFrame(results)


def generate_detection_id(window_start: datetime, prefix: str, origin_as: int) -> str:
    """
    Generate deterministic detection ID from key fields.
    
    Args:
        window_start: Time window
        prefix: IP prefix
        origin_as: Origin AS number
        
    Returns:
        Deterministic detection ID string
    """
    key = f"{window_start.isoformat()}|{prefix}|{origin_as}"
    hash_hex = hashlib.sha256(key.encode()).hexdigest()[:16]
    return f"ml_{hash_hex}"


def insert_hybrid_anomaly_detections(
    conn: Connection,
    df: pd.DataFrame,
    scores_df: pd.DataFrame
) -> int:
    """
    Insert detection results into hybrid_anomaly_detections table.
    
    Args:
        conn: Database connection
        df: Original features DataFrame
        scores_df: Scores DataFrame from compute_z_score_ensemble
        
    Returns:
        Number of rows inserted
    """
    inserted = 0
    
    with conn.cursor() as cur:
        for i, row in df.iterrows():
            score_row = scores_df.iloc[i]
            
            # Generate detection ID
            detection_id = generate_detection_id(
                row['window_start'],
                row['prefix'],
                row['origin_as']
            )
            
            # Build metadata JSON
            metadata = {
                "iso_score": float(score_row['iso_raw']),
                "lstm_score": float(score_row['lstm_raw']),
                "z_iso": float(score_row['z_iso']),
                "z_lstm": float(score_row['z_lstm']),
                "ensemble_method": ENSEMBLE_METHOD,
                "model_version": MODEL_VERSION,
                "feature_columns": FEATURE_COLUMNS,
                "threshold": ANOMALY_THRESHOLD
            }
            
            # Insert detection
            insert_query = """
                INSERT INTO hybrid_anomaly_detections (
                    timestamp,
                    detection_id,
                    prefix,
                    prefix_length,
                    peer_ip,
                    peer_asn,
                    origin_as,
                    as_path,
                    next_hop,
                    event_type,
                    message_type,
                    rpki_status,
                    rpki_anomaly,
                    combined_anomaly,
                    combined_score,
                    combined_severity,
                    classification,
                    metadata
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (detection_id) DO UPDATE SET
                    combined_score = EXCLUDED.combined_score,
                    combined_anomaly = EXCLUDED.combined_anomaly,
                    combined_severity = EXCLUDED.combined_severity,
                    metadata = EXCLUDED.metadata
            """
            
            try:
                # Extract prefix length from prefix string
                prefix_str = str(row['prefix'])
                prefix_length = int(prefix_str.split('/')[-1]) if '/' in prefix_str else 32
                
                cur.execute(insert_query, (
                    row['window_start'],
                    detection_id,
                    prefix_str,
                    prefix_length,
                    None,  # peer_ip - not available in features table
                    None,  # peer_asn - would need to join
                    int(row['origin_as']),
                    None,  # as_path
                    None,  # next_hop
                    'ml_anomaly',
                    'bgp_features_5min',
                    'unknown',
                    False,  # rpki_anomaly
                    bool(score_row['combined_anomaly']),
                    float(score_row['combined_score']),
                    score_row['combined_severity'],
                    'lstm_if_ensemble',
                    psycopg.types.json.Json(metadata)
                ))
                inserted += 1
            except Exception as e:
                logger.error(f"Failed to insert detection for {detection_id}: {e}")
    
    return inserted


def main():
    """
    Main service loop for ML inference.
    """
    logger.info("Starting ML Inference Service for BGP Anomaly Detection")
    logger.info(f"Configuration:")
    logger.info(f"  - Ensemble method: {ENSEMBLE_METHOD}")
    logger.info(f"  - Anomaly threshold: {ANOMALY_THRESHOLD}")
    logger.info(f"  - Poll interval: {POLL_INTERVAL}s")
    logger.info(f"  - LSTM sequence length: {LSTM_SEQUENCE_LENGTH}")
    
    # Connect to database
    try:
        conn = get_db_connection()
        logger.info("[OK] Connected to database")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)
    
    # Initialize state table
    try:
        init_state_table(conn)
    except Exception as e:
        logger.error(f"Failed to initialize state table: {e}")
        sys.exit(1)
    
    # Load models
    try:
        models = load_models_and_baseline()
        logger.info("[OK] All models loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load models: {e}")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("ML Inference Service is now running")
    logger.info("=" * 60)
    
    # Main loop
    iteration = 0
    while True:
        iteration += 1
        logger.info(f"\n--- Iteration {iteration} ---")
        
        try:
            # Get last processed timestamp
            last_ts = get_last_processed_timestamp(conn)
            logger.debug(f"Last processed timestamp: {last_ts}")
            
            # Fetch new feature rows
            df = fetch_new_feature_rows(conn, last_ts)
            
            if len(df) == 0:
                logger.info("No new feature rows to process")
            else:
                logger.info(f"Processing {len(df)} feature rows...")
                
                # Compute Isolation Forest scores
                logger.info("Computing Isolation Forest scores...")
                iso_scores = compute_iso_scores(df, models)
                
                # Compute LSTM scores
                logger.info("Computing LSTM scores...")
                lstm_scores = compute_lstm_scores(df, models)
                
                # Compute ensemble
                logger.info("Computing z-score ensemble...")
                scores_df = compute_z_score_ensemble(iso_scores, lstm_scores, df, models)
                
                # Count anomalies
                anomaly_count = scores_df['combined_anomaly'].sum()
                logger.info(f"Detected {anomaly_count} anomalies out of {len(df)} rows")
                
                # Insert detections
                logger.info("Inserting detections into database...")
                inserted = insert_hybrid_anomaly_detections(conn, df, scores_df)
                logger.info(f"[OK] Inserted {inserted} detection records")
                
                # Update state
                last_window = df['window_start'].max()
                update_state(conn, last_window, len(df))
                logger.info(f"[OK] Updated state: last_processed = {last_window}")
            
        except KeyboardInterrupt:
            logger.info("\nReceived shutdown signal, exiting...")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
        
        # Sleep before next iteration
        logger.info(f"Sleeping for {POLL_INTERVAL} seconds...")
        time.sleep(POLL_INTERVAL)
    
    # Cleanup
    conn.close()
    logger.info("ML Inference Service stopped")


if __name__ == "__main__":
    main()
