#!/usr/bin/env python3
"""
Correlation & Classification Engine - Phase 3 Implementation
Document Section 6 Step 7 & Section 10 Decision Matrix

Combines signals from:
- Heuristic detector
- ML models (Isolation Forest + LSTM)
- RPKI validator

Produces final classification:
- NORMAL: Low severity, single weak signal
- SUSPICIOUS: Multi-detector signals without RPKI confirmation
- INVALID: RPKI Invalid + Heuristic anomalies
- HIJACK: RPKI Origin Mismatch (Critical)
- LEAK: RPKI MaxLength Violation (High) + Path inflation

Multi-source severity escalation (Document Section 10):
- 2 sources → Medium
- 3 sources → High
- ≥4 sources → Critical
"""

import psycopg2
from psycopg2.extras import RealDictCursor, Json
import pandas as pd
from datetime import datetime, timedelta, timezone
import time
import logging
import sys
from collections import defaultdict

# ===================== Configuration =====================
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'bgp_ensemble_db',
    'user': 'postgres',
    'password': 'your_password_here'
}

POLL_INTERVAL = 20  # Poll every 20 seconds
TIME_WINDOW = 60  # Correlation window: 60 seconds (group detections within 1 minute)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('correlation_engine.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('correlation_engine')

# ===================== Database Functions =====================

def get_db_connection():
    """Establish connection to PostgreSQL database."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def get_last_processed_id(conn):
    """Retrieve the last processed detection ID from state table."""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COALESCE(last_processed_id, 0) as last_processed_id FROM correlation_engine_state WHERE id = 1")
            result = cur.fetchone()
            return result['last_processed_id'] if result else 0
    except Exception as e:
        logger.error(f"Error getting last processed ID: {e}")
        conn.rollback()
        return 0

def fetch_new_detections(conn, last_processed_id):
    """
    Fetch new detections from hybrid_anomaly_detections that haven't been correlated yet.
    """
    try:
        query = """
            SELECT 
                id, timestamp, detection_id, prefix, prefix_length,
                origin_as, event_type, rpki_status, rpki_anomaly,
                combined_anomaly, combined_score, combined_severity,
                classification, metadata
            FROM hybrid_anomaly_detections
            WHERE id > %s
            ORDER BY id ASC
        """
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (last_processed_id,))
            rows = cur.fetchall()
            
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        logger.info(f"Fetched {len(df)} new detections for correlation")
        return df
        
    except Exception as e:
        logger.error(f"Error fetching new detections: {e}")
        return pd.DataFrame()

def update_state(conn, last_id, count):
    """Update the correlation engine state table."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE correlation_engine_state
                SET last_processed_id = %s,
                    total_processed = total_processed + %s,
                    last_update = NOW()
                WHERE id = 1
            """, (last_id, count))
        conn.commit()
        logger.info(f"Updated state: last_id={last_id}, processed={count}")
    except Exception as e:
        logger.error(f"Error updating state: {e}")
        conn.rollback()

def batch_update_detections(conn, updates):
    """
    Batch update multiple detections at once for performance.
    
    Args:
        conn: Database connection
        updates: List of tuples (classification, final_severity, metadata_update, detection_id)
    """
    if not updates:
        return
    
    try:
        with conn.cursor() as cur:
            # Use execute_batch for efficient bulk updates
            from psycopg2.extras import execute_batch
            
            execute_batch(cur, """
                UPDATE hybrid_anomaly_detections
                SET classification = %s,
                    combined_severity = %s,
                    metadata = metadata || %s::jsonb
                WHERE detection_id = %s
            """, updates, page_size=500)
        
        conn.commit()
        logger.info(f"Batch updated {len(updates)} detections")
    except Exception as e:
        logger.error(f"Error in batch update: {e}")
        conn.rollback()
        raise

# ===================== Classification Logic =====================

def classify_detection_group(detections_df):
    """
    Classify a group of detections for the same prefix/origin within time window.
    
    Document Section 10 Decision Matrix:
    - HIJACK: RPKI Origin Mismatch (Critical)
    - LEAK: RPKI MaxLength Violation (High) + Path inflation
    - INVALID: RPKI Invalid + Heuristic anomalies
    - SUSPICIOUS: Multi-detector signals without RPKI confirmation
    - NORMAL: Low severity, single weak signal
    
    Args:
        detections_df: DataFrame of detections for same prefix/origin/window
    
    Returns:
        Tuple: (classification, final_severity, source_count, reasoning)
    """
    
    # Count unique detection sources
    event_types = detections_df['event_type'].unique()
    source_count = len(event_types)
    
    # Check for RPKI signals
    rpki_detections = detections_df[detections_df['event_type'] == 'rpki']
    has_rpki_invalid = False
    has_rpki_origin_mismatch = False
    has_rpki_maxlength = False
    
    if not rpki_detections.empty:
        rpki_invalid = rpki_detections[rpki_detections['rpki_status'] == 'invalid']
        if not rpki_invalid.empty:
            has_rpki_invalid = True
            # Check metadata for specific RPKI violation type
            for _, row in rpki_invalid.iterrows():
                metadata = row.get('metadata', {})
                if isinstance(metadata, dict):
                    desc = metadata.get('rpki_description', '').lower()
                    if 'origin as mismatch' in desc or 'hijack' in desc:
                        has_rpki_origin_mismatch = True
                    if 'maxlength' in desc or 'leak' in desc:
                        has_rpki_maxlength = True
    
    # Check for heuristic signals
    heuristic_detections = detections_df[detections_df['event_type'] == 'heuristic']
    has_heuristic = not heuristic_detections.empty
    has_path_inflation = False
    
    if has_heuristic:
        for _, row in heuristic_detections.iterrows():
            metadata = row.get('metadata', {})
            if isinstance(metadata, dict):
                rules = metadata.get('triggered_rules', [])
                if 'path_inflation' in rules:
                    has_path_inflation = True
    
    # Check for ML signals
    has_ml = 'ml_anomaly' in event_types
    
    # Get highest individual severity
    severity_order = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
    max_severity = max(detections_df['combined_severity'].apply(lambda x: severity_order.get(x, 0)))
    max_severity_label = [k for k, v in severity_order.items() if v == max_severity][0]
    
    # Classification Logic (Document Section 10)
    
    # HIJACK: RPKI Origin Mismatch = Critical
    if has_rpki_origin_mismatch:
        return ('HIJACK', 'critical', source_count, 'RPKI Origin AS mismatch detected - hijack signal')
    
    # LEAK: RPKI MaxLength Violation + Path inflation = High
    if has_rpki_maxlength and has_path_inflation:
        return ('LEAK', 'critical', source_count, 'RPKI MaxLength violation + Path inflation - route leak')
    
    # LEAK: RPKI MaxLength Violation alone = High
    if has_rpki_maxlength:
        return ('LEAK', 'high', source_count, 'RPKI MaxLength violation - potential route leak')
    
    # INVALID: RPKI Invalid (generic) + Heuristic anomalies
    if has_rpki_invalid and has_heuristic:
        return ('INVALID', 'high', source_count, 'RPKI invalid + Heuristic anomalies detected')
    
    # INVALID: RPKI Invalid alone
    if has_rpki_invalid:
        return ('INVALID', 'high', source_count, 'RPKI validation failed')
    
    # Multi-source severity escalation (Document Section 10)
    # ≥4 sources → Critical
    if source_count >= 4:
        return ('SUSPICIOUS', 'critical', source_count, f'Severe systemic issue - {source_count} detection sources')
    
    # 3 sources → High
    if source_count == 3:
        return ('SUSPICIOUS', 'high', source_count, 'Broad evidence - 3 detection sources')
    
    # 2 sources → Medium
    if source_count == 2:
        return ('SUSPICIOUS', 'medium', source_count, 'Stronger evidence - 2 detection sources')
    
    # Single source - use original severity
    if source_count == 1:
        if max_severity_label in ['high', 'critical']:
            return ('SUSPICIOUS', max_severity_label, source_count, f'Single detector with {max_severity_label} severity')
        else:
            return ('NORMAL', max_severity_label, source_count, 'Single weak signal - informational')
    
    # Fallback
    return ('NORMAL', 'low', source_count, 'No significant anomaly')

# ===================== Correlation Logic =====================

def correlate_detections(df, conn):
    """
    Correlate detections by grouping them by (prefix, origin_as, time_window).
    Apply classification logic and update records.
    
    Args:
        df: DataFrame of new detections
        conn: Database connection
    
    Returns:
        int: Number of detection groups correlated
    """
    if df.empty:
        return 0
    
    # Add time window grouping (round to nearest minute)
    df['time_window'] = pd.to_datetime(df['timestamp']).dt.floor(f'{TIME_WINDOW}s')
    
    # Group by (prefix, origin_as, time_window)
    grouped = df.groupby(['prefix', 'origin_as', 'time_window'])
    
    correlation_count = 0
    classification_stats = defaultdict(int)
    
    # Collect all updates in a batch
    batch_updates = []
    
    for (prefix, origin_as, time_window), group_df in grouped:
        # Apply classification logic
        classification, final_severity, source_count, reasoning = classify_detection_group(group_df)
        
        classification_stats[classification] += 1
        
        # Prepare updates for all detections in this group
        for _, row in group_df.iterrows():
            metadata_update = {
                'correlation': {
                    'source_count': source_count,
                    'classification': classification,
                    'final_severity': final_severity,
                    'reasoning': reasoning,
                    'time_window': time_window.isoformat(),
                    'correlated_at': datetime.now(timezone.utc).isoformat()
                }
            }
            
            # Add to batch (classification, severity, metadata, detection_id)
            batch_updates.append((
                classification,
                final_severity,
                Json(metadata_update),
                row['detection_id']
            ))
        
        correlation_count += 1
        
        # Log every 50 groups to show progress
        if correlation_count % 50 == 0:
            logger.info(f"Progress: {correlation_count} groups processed, {len(batch_updates)} updates queued")
    
    # Execute all updates in one batch
    if batch_updates:
        logger.info(f"Executing batch update for {len(batch_updates)} detections...")
        batch_update_detections(conn, batch_updates)
        logger.info(f"Batch update complete")
    
    # Log summary
    logger.info(f"Classification summary: {dict(classification_stats)}")
    
    return correlation_count

# ===================== Main Processing Loop =====================

def main():
    """Main processing loop for correlation engine."""
    logger.info("="*60)
    logger.info("Correlation & Classification Engine Starting")
    logger.info(f"Poll Interval: {POLL_INTERVAL}s")
    logger.info(f"Time Window: {TIME_WINDOW}s")
    logger.info("="*60)
    
    conn = get_db_connection()
    logger.info("[OK] Database connection established")
    
    try:
        iteration = 0
        while True:
            iteration += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"Iteration {iteration} - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'='*60}")
            
            # Get last processed ID
            last_processed_id = get_last_processed_id(conn)
            logger.info(f"Last processed ID: {last_processed_id}")
            
            # Fetch new detections
            df = fetch_new_detections(conn, last_processed_id)
            
            if not df.empty:
                logger.info(f"Processing {len(df)} detections...")
                
                # Correlate and classify
                correlation_count = correlate_detections(df, conn)
                
                logger.info(f"Correlation complete: {correlation_count} groups processed")
                
                # Update state
                last_id = df['id'].max()
                update_state(conn, int(last_id), len(df))
                
            else:
                logger.info("No new detections to process")
            
            # Wait before next poll
            logger.info(f"Sleeping for {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("\nShutting down correlation engine...")
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")
        raise
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed")

if __name__ == "__main__":
    main()
