#!/usr/bin/env python3
"""
RPKI Validator Service - Phase 3 Implementation
Validates BGP route announcements against RPKI (Resource Public Key Infrastructure)

Implements 100% document specification:
- Origin AS mismatch (origin_as != ROA.origin_as) → Critical severity (hijack signal)
- MaxLength violation (prefix_length > max_length) → High severity (leak/config error)
- Unknown ROA (no matching VRP) → Low severity (informational)
- Valid ROA → No detection (normal traffic)

Architecture:
- Polls bgp_features_1min table for new aggregated features
- Queries Routinator HTTP API for RPKI validation
- Writes anomaly detections to hybrid_anomaly_detections
- State tracking via rpki_inference_state table
"""

import psycopg2
from psycopg2.extras import RealDictCursor, Json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import time
import logging
import sys
import requests
from ipaddress import ip_network
import json

# ===================== Configuration =====================
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'bgp_ensemble_db',
    'user': 'postgres',
    'password': 'your_password_here'
}

ROUTINATOR_API_URL = "http://localhost:8323/api/v1/validity"
POLL_INTERVAL = 30  # Poll every 30 seconds (slower than heuristics due to API calls)
REQUEST_TIMEOUT = 5  # Timeout for Routinator API requests
MAX_RETRIES = 3  # Maximum retries for failed API calls

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rpki_validator.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('rpki_validator')

# ===================== Database Functions =====================

def get_db_connection():
    """Establish connection to PostgreSQL database."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def get_last_processed_timestamp(conn):
    """Retrieve the last processed timestamp from state table."""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT last_processed_timestamp 
                FROM rpki_inference_state 
                WHERE id = 1
            """)
            result = cur.fetchone()
            if result and result['last_processed_timestamp']:
                return result['last_processed_timestamp']
            else:
                # Default to 1 hour ago if no state exists
                return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    except Exception as e:
        logger.error(f"Error getting last processed timestamp: {e}")
        return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)

def fetch_new_features(conn, last_processed_timestamp):
    """
    Fetch new feature rows from bgp_features_1min that haven't been processed yet.
    Returns a DataFrame with the relevant columns for RPKI validation.
    """
    try:
        query = """
            SELECT 
                window_start,
                prefix,
                origin_as,
                path_length,
                announcements,
                withdrawals,
                unique_peers
            FROM bgp_features_1min
            WHERE window_start > %s
            ORDER BY window_start ASC
        """
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (last_processed_timestamp,))
            rows = cur.fetchall()
            
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        logger.info(f"Fetched {len(df)} new feature rows for RPKI validation")
        return df
        
    except Exception as e:
        logger.error(f"Error fetching new features: {e}")
        return pd.DataFrame()

def update_state(conn, last_timestamp, processed_count):
    """Update the inference state table with the latest processed timestamp."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE rpki_inference_state
                SET last_processed_timestamp = %s,
                    total_processed = total_processed + %s,
                    last_update = NOW()
                WHERE id = 1
            """)
        conn.commit()
        logger.info(f"Updated state: last_timestamp={last_timestamp}, processed={processed_count}")
    except Exception as e:
        logger.error(f"Error updating state: {e}")
        conn.rollback()

def insert_rpki_detection(conn, row, rpki_result):
    """
    Insert RPKI anomaly detection into hybrid_anomaly_detections table.
    
    Args:
        row: Feature row from bgp_features_1min
        rpki_result: Tuple of (validity_state, severity, description, vrps)
    """
    validity_state, severity, description, vrps = rpki_result
    
    try:
        prefix_length = get_prefix_length(row['prefix'])
        detection_id = f"rpki_{row['window_start'].strftime('%Y%m%d%H%M%S')}_{row['prefix']}_{row['origin_as']}"
        
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO hybrid_anomaly_detections (
                    timestamp, detection_id, prefix, prefix_length,
                    peer_ip, peer_asn, origin_as, as_path, next_hop,
                    event_type, message_type, rpki_status, rpki_anomaly,
                    combined_anomaly, combined_score, combined_severity,
                    classification, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (detection_id) DO NOTHING
            """, (
                row['window_start'],
                detection_id,
                str(row['prefix']),
                prefix_length,
                None,
                None,
                row['origin_as'],
                None,
                None,
                'rpki',
                'rpki_validation',
                validity_state,
                True if validity_state in ['invalid', 'unknown'] else False,
                True,
                get_severity_score(severity),
                severity,
                'UNKNOWN',
                Json({
                    'vrps': vrps,
                    'validation_time': datetime.now(timezone.utc).isoformat(),
                    'announcements': int(row['announcements']),
                    'withdrawals': int(row['withdrawals']),
                    'unique_peers': int(row['unique_peers']),
                    'rpki_description': description
                })
            ))
        conn.commit()
        logger.info(f"Inserted RPKI detection: {validity_state}/{severity} - {row['prefix']} AS{row['origin_as']}")
    except Exception as e:
        logger.error(f"Error inserting RPKI detection: {e}")
        conn.rollback()

# ===================== RPKI Validation Functions =====================

def get_prefix_length(prefix_str):
    """Extract prefix length from CIDR notation (e.g., '1.1.1.0/24' → 24)."""
    try:
        return int(prefix_str.split('/')[1])
    except:
        return None

def query_routinator_api(asn, prefix):
    """
    Query Routinator API for RPKI validation.
    
    Args:
        asn: Origin AS number
        prefix: IP prefix in CIDR notation (e.g., '1.1.1.0/24')
    
    Returns:
        dict: Routinator API response or None if failed
    """
    try:
        # Parse prefix to get network and length
        network = ip_network(prefix, strict=False)
        ip_addr = str(network.network_address)
        prefix_length = network.prefixlen
        
        # Construct API URL: /api/v1/validity/{asn}/{prefix}/{length}
        url = f"{ROUTINATOR_API_URL}/{asn}/{ip_addr}/{prefix_length}"
        
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(url, timeout=REQUEST_TIMEOUT)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 503:
                    # Initial validation ongoing
                    logger.warning(f"Routinator initializing, waiting... (attempt {attempt+1}/{MAX_RETRIES})")
                    time.sleep(5)
                    continue
                else:
                    logger.warning(f"Routinator API returned status {response.status_code} for {prefix} AS{asn}")
                    return None
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Routinator API timeout (attempt {attempt+1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2)
                continue
            except requests.exceptions.ConnectionError:
                logger.error(f"Cannot connect to Routinator API at {ROUTINATOR_API_URL}")
                return None
                
        return None
        
    except Exception as e:
        logger.error(f"Error querying Routinator API: {e}")
        return None

def validate_rpki(row, conn):
    """
    Validate BGP announcement against RPKI using 100% document logic.
    
    Document specification:
    1. Origin AS mismatch (origin_as != ROA.origin_as) → Critical severity (hijack signal)
    2. MaxLength violation (prefix_length > max_length) → High severity (leak/config error)
    3. Unknown ROA (no matching VRP) → Low severity (informational)
    4. Valid ROA → No detection (normal traffic)
    
    Args:
        row: Feature row from bgp_features_1min
        conn: Database connection
    
    Returns:
        Tuple: (validity_state, severity, description, vrps) or None if valid/no detection
    """
    try:
        prefix = row['prefix']
        origin_as = int(row['origin_as'])
        prefix_length = get_prefix_length(prefix)
        
        if prefix_length is None:
            logger.warning(f"Invalid prefix format: {prefix}")
            return None
        
        # Query Routinator API
        api_response = query_routinator_api(origin_as, prefix)
        
        if api_response is None:
            # API unavailable - skip this validation
            return None
        
        # Parse Routinator response
        validated_route = api_response.get('validated_route', {})
        validity = validated_route.get('validity', {})
        state = validity.get('state', 'unknown')
        vrps = validated_route.get('vrps', {})
        
        # Document Logic Implementation
        
        if state == 'valid':
            # Valid RPKI - no detection needed
            return None
        
        elif state == 'invalid':
            # Invalid RPKI - determine if Origin mismatch or MaxLength violation
            reason = validity.get('reason', '')
            
            # Check for Origin AS mismatch (Critical - hijack signal)
            if 'as' in reason.lower() or 'origin' in reason.lower():
                # Extract ROA information
                matched_vrps = vrps.get('matched', [])
                unmatched_vrps = vrps.get('unmatched', [])
                
                roa_origins = []
                for vrp_list in [matched_vrps, unmatched_vrps]:
                    for vrp in vrp_list:
                        roa_origin = vrp.get('asn')
                        if roa_origin and roa_origin != origin_as:
                            roa_origins.append(roa_origin)
                
                if roa_origins:
                    description = f"Origin AS mismatch: announced AS{origin_as}, ROA expects AS{roa_origins[0]} - HIJACK SIGNAL"
                    return ('invalid', 'critical', description, vrps)
            
            # Check for MaxLength violation (High - leak/config error)
            if 'length' in reason.lower() or 'max' in reason.lower():
                # Extract max_length from VRPs
                matched_vrps = vrps.get('matched', [])
                for vrp in matched_vrps:
                    max_length = vrp.get('max_length')
                    if max_length and prefix_length > max_length:
                        description = f"MaxLength violation: prefix /{prefix_length} exceeds max_length /{max_length} - LEAK/CONFIG ERROR"
                        return ('invalid', 'high', description, vrps)
            
            # Generic invalid (if we couldn't determine specific reason)
            description = f"RPKI invalid: {reason}"
            return ('invalid', 'high', description, vrps)
        
        elif state == 'not-found' or state == 'unknown':
            # Unknown RPKI - no ROA found (Low - informational)
            description = f"No ROA found for prefix {prefix} origin AS{origin_as} - INFORMATIONAL"
            return ('unknown', 'low', description, vrps)
        
        else:
            logger.warning(f"Unexpected RPKI state: {state} for {prefix} AS{origin_as}")
            return None
            
    except Exception as e:
        logger.error(f"Error validating RPKI for {row.get('prefix')} AS{row.get('origin_as')}: {e}")
        return None

def get_severity_score(severity):
    """Convert severity level to numeric score (1-10) for combined_score."""
    severity_map = {
        'critical': 10,
        'high': 7,
        'medium': 5,
        'low': 2
    }
    return severity_map.get(severity.lower(), 5)

# ===================== Main Processing Loop =====================

def process_feature_rows(df, conn):
    """
    Process a batch of feature rows for RPKI validation.
    
    Args:
        df: DataFrame of feature rows from bgp_features_1min
        conn: Database connection
    
    Returns:
        int: Number of detections found
    """
    if df.empty:
        return 0
    
    detection_count = 0
    
    for idx, row in df.iterrows():
        try:
            # Validate against RPKI
            rpki_result = validate_rpki(row, conn)
            
            if rpki_result is not None:
                # Detection found - insert into database
                insert_rpki_detection(conn, row, rpki_result)
                detection_count += 1
            
        except Exception as e:
            logger.error(f"Error processing row {idx}: {e}")
            continue
    
    return detection_count

def wait_for_routinator(max_wait_seconds=60):
    """
    Wait for Routinator to become available and complete initial validation.
    Routinator needs ~30 seconds after Docker start to download ROAs.
    """
    logger.info("Waiting for Routinator to be ready...")
    start_time = time.time()
    attempt = 0
    
    while time.time() - start_time < max_wait_seconds:
        attempt += 1
        try:
            url = f"{ROUTINATOR_API_URL}/13335/1.1.1.0/24"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                logger.info(f"[OK] Routinator is ready (took {int(time.time() - start_time)}s)")
                return True
            elif response.status_code == 503:
                logger.info(f"Routinator initializing... (attempt {attempt}, {int(time.time() - start_time)}s elapsed)")
                time.sleep(5)
            else:
                logger.warning(f"Unexpected Routinator response: {response.status_code}")
                time.sleep(5)
                
        except requests.exceptions.ConnectionError:
            logger.warning(f"Routinator not yet available (attempt {attempt})")
            time.sleep(5)
        except Exception as e:
            logger.warning(f"Error checking Routinator: {e}")
            time.sleep(5)
    
    logger.error(f"Routinator did not become ready within {max_wait_seconds}s")
    return False

def main():
    """Main entry point for RPKI validation service."""
    logger.info("="*60)
    logger.info("RPKI Validator Service Starting")
    logger.info(f"Routinator API: {ROUTINATOR_API_URL}")
    logger.info(f"Poll Interval: {POLL_INTERVAL}s")
    logger.info("="*60)
    
    # Wait for Routinator to be ready (handles Docker startup delay)
    if not wait_for_routinator(max_wait_seconds=60):
        logger.error("Cannot connect to Routinator API. Please ensure Routinator is running.")
        logger.error("Start Routinator with: docker run -d -p 8323:8323 nlnetlabs/routinator server --http 0.0.0.0:8323")
        sys.exit(1)
    
    conn = get_db_connection()
    logger.info("[OK] Database connection established")
    
    try:
        iteration = 0
        while True:
            iteration += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"Iteration {iteration} - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'='*60}")
            
            # Get last processed timestamp
            last_processed = get_last_processed_timestamp(conn)
            logger.info(f"Last processed: {last_processed}")
            
            # Fetch new features
            df = fetch_new_features(conn, last_processed)
            
            if not df.empty:
                logger.info(f"Processing {len(df)} feature rows...")
                
                # Process features for RPKI validation
                detection_count = process_feature_rows(df, conn)
                
                logger.info(f"RPKI validation complete: {detection_count} detections")
                
                # Update state
                last_timestamp = df['window_start'].max()
                update_state(conn, last_timestamp, len(df))
                
            else:
                logger.info("No new features to process")
            
            # Wait before next poll
            logger.info(f"Sleeping for {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("\nShutting down RPKI validator service...")
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")
        raise
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed")

if __name__ == "__main__":
    main()
