#!/usr/bin/env python3
"""
Heuristic Detector Service for BGP Anomaly Detection

Applies deterministic rule-based detection on bgp_features_1min data.
Runs as a standalone service alongside ML-based detectors.
"""

import os
import sys
import time
import logging
import hashlib
import ipaddress
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import psycopg
from psycopg import Connection
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Configuration
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))  # seconds
VERSION = "v1.0"

# Document thresholds (from Bgp Monitoring System design)
# Converted from 5-min windows to 1-min windows (multiply by 12 for hourly rate)
THRESHOLDS = {
    "churn": {
        "moderate": 1212,  # 101 updates/5min = 1212/hr
        "severe": 6012,    # 501 updates/5min = 6012/hr
        "critical": 24000  # 2000 updates/5min = 24000/hr
    },
    "flapping": {
        "medium": 132,     # 11 flaps/5min = 132/hr
        "high": 372,       # 31 flaps/5min = 372/hr
        "critical": 1200   # 100 flaps/5min = 1200/hr
    },
    "path_length": {
        "mild": 16,        # Suspicious threshold
        "severe": 25       # Critical threshold
    },
    "withdrawal_ratio": {
        "high": 0.70,
        "critical": 0.90
    },
    "path_inflation": {
        "high": 5,         # Path length increase >5 from baseline
        "critical": 10     # Path length increase >10 from baseline
    },
    "volume_spike": {
        "high": 100000,    # 100k-500k msg/min
        "critical": 500000 # >500k msg/min
    },
    "session_resets": {
        "medium": 6,       # 6-10 resets
        "high": 11,        # 11-50 resets
        "critical": 50     # >50 resets
    }
}

# Bogon ASN ranges (private use)
BOGON_ASN_RANGES = [
    (64512, 65534),              # RFC 6996: Private Use 16-bit
    (4200000000, 4294967294)     # RFC 6996: Private Use 32-bit
]

# Bogon prefixes (should never be routed)
BOGON_PREFIXES = [
    "0.0.0.0/8",        # RFC 1122: This network
    "10.0.0.0/8",       # RFC 1918: Private-Use
    "100.64.0.0/10",    # RFC 6598: Shared Address Space
    "127.0.0.0/8",      # RFC 1122: Loopback
    "169.254.0.0/16",   # RFC 3927: Link Local
    "172.16.0.0/12",    # RFC 1918: Private-Use
    "192.0.0.0/24",     # RFC 6890: IETF Protocol Assignments
    "192.0.2.0/24",     # RFC 5737: Documentation (TEST-NET-1)
    "192.168.0.0/16",   # RFC 1918: Private-Use
    "198.18.0.0/15",    # RFC 2544: Benchmarking
    "198.51.100.0/24",  # RFC 5737: Documentation (TEST-NET-2)
    "203.0.113.0/24",   # RFC 5737: Documentation (TEST-NET-3)
    "224.0.0.0/4",      # RFC 5771: Multicast
    "240.0.0.0/4",      # RFC 1112: Reserved
    "255.255.255.255/32" # RFC 919: Limited Broadcast
]


@dataclass
class HeuristicHit:
    """Result of a single heuristic rule check"""
    rule_name: str
    severity: str    # "low" | "medium" | "high" | "critical"
    score: float     # 0-1
    reason: str


def build_dsn() -> str:
    """Build PostgreSQL DSN from environment variables"""
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "bgp_ensemble_db")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "your_password_here")
    
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def get_db_connection(dsn: str) -> Connection:
    """Connect to PostgreSQL with autocommit"""
    conn = psycopg.connect(dsn, autocommit=True)
    return conn


def init_state_table(conn: Connection) -> None:
    """Ensure state table exists"""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS heuristic_inference_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            last_processed_timestamp TIMESTAMP WITHOUT TIME ZONE,
            total_processed BIGINT DEFAULT 0,
            last_update TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            CHECK (id = 1)
        )
    """)
    cur.close()
    logger.info("State table verified")


def get_last_processed_timestamp(conn: Connection) -> datetime:
    """Get last processed timestamp from state table"""
    cur = conn.cursor()
    cur.execute("SELECT last_processed_timestamp FROM heuristic_inference_state WHERE id = 1")
    row = cur.fetchone()
    cur.close()
    
    if row and row[0]:
        return row[0]
    else:
        # Default to 10 minutes ago
        default_ts = datetime.now(timezone.utc).replace(tzinfo=None)
        return default_ts


def update_state(conn: Connection, last_ts: datetime, processed_count: int) -> None:
    """Update state table with latest timestamp and count"""
    cur = conn.cursor()
    cur.execute("""
        UPDATE heuristic_inference_state 
        SET last_processed_timestamp = %s,
            total_processed = total_processed + %s,
            last_update = NOW()
        WHERE id = 1
    """, (last_ts, processed_count))
    cur.close()


def check_churn(row: Dict[str, Any]) -> Optional[HeuristicHit]:
    """
    Check for churn anomalies (high update rate).
    
    Churn rate = total_updates * 60 (extrapolated to per-hour for 1-min windows)
    """
    total_updates = row.get('total_updates', 0)
    churn_per_hour = total_updates * 60
    
    if churn_per_hour > THRESHOLDS["churn"]["critical"]:
        return HeuristicHit(
            rule_name="churn_critical",
            severity="critical",
            score=0.95,
            reason=f"total_updates={total_updates} ({churn_per_hour:.0f}/hr) exceeds critical threshold {THRESHOLDS['churn']['critical']}/hr"
        )
    elif churn_per_hour > THRESHOLDS["churn"]["severe"]:
        return HeuristicHit(
            rule_name="churn_severe",
            severity="high",
            score=0.8,
            reason=f"total_updates={total_updates} ({churn_per_hour:.0f}/hr) exceeds severe threshold {THRESHOLDS['churn']['severe']}/hr"
        )
    elif churn_per_hour > THRESHOLDS["churn"]["moderate"]:
        return HeuristicHit(
            rule_name="churn_moderate",
            severity="medium",
            score=0.6,
            reason=f"total_updates={total_updates} ({churn_per_hour:.0f}/hr) exceeds moderate threshold {THRESHOLDS['churn']['moderate']}/hr"
        )
    
    return None


def check_withdrawal_ratio(row: Dict[str, Any]) -> Optional[HeuristicHit]:
    """
    Check for withdrawal storms (high ratio + significant volume).
    
    Requires BOTH high withdrawal ratio AND substantial volume to distinguish
    real anomalies (storms during attacks) from routine operations (cleanup).
    """
    ratio = row.get('withdrawal_ratio', 0.0)
    withdrawals = row.get('withdrawals', 0)
    withdrawals_per_hour = withdrawals * 60  # 1-min window → hourly rate
    
    # Critical: ratio >= 0.90 AND >300 withdrawals/hour
    if ratio >= THRESHOLDS["withdrawal_ratio"]["critical"] and withdrawals_per_hour > 300:
        return HeuristicHit(
            rule_name="withdrawal_storm_critical",
            severity="critical",
            score=0.95,
            reason=f"withdrawal_ratio={ratio:.2f}, withdrawals={withdrawals} ({withdrawals_per_hour:.0f}/hr) - withdrawal storm detected"
        )
    # High: ratio >= 0.70 AND >600 withdrawals/hour (higher volume needed for lower ratio)
    elif ratio >= THRESHOLDS["withdrawal_ratio"]["high"] and withdrawals_per_hour > 600:
        return HeuristicHit(
            rule_name="withdrawal_storm_high",
            severity="high",
            score=0.8,
            reason=f"withdrawal_ratio={ratio:.2f}, withdrawals={withdrawals} ({withdrawals_per_hour:.0f}/hr) - high withdrawal activity"
        )
    
    return None


def check_flapping(row: Dict[str, Any]) -> Optional[HeuristicHit]:
    """
    Check for route flapping (frequent announce/withdraw cycles).
    
    Flap rate = flap_count * 60 (extrapolated to per-hour for 1-min windows)
    """
    flap_count = row.get('flap_count', 0)
    flap_per_hour = flap_count * 60
    
    if flap_per_hour > THRESHOLDS["flapping"]["critical"]:
        return HeuristicHit(
            rule_name="flap_critical",
            severity="critical",
            score=0.95,
            reason=f"flap_count={flap_count} ({flap_per_hour:.0f}/hr) exceeds critical threshold {THRESHOLDS['flapping']['critical']}/hr"
        )
    elif flap_per_hour > THRESHOLDS["flapping"]["high"]:
        return HeuristicHit(
            rule_name="flap_high",
            severity="high",
            score=0.8,
            reason=f"flap_count={flap_count} ({flap_per_hour:.0f}/hr) exceeds high threshold {THRESHOLDS['flapping']['high']}/hr"
        )
    elif flap_per_hour > THRESHOLDS["flapping"]["medium"]:
        return HeuristicHit(
            rule_name="flap_medium",
            severity="medium",
            score=0.6,
            reason=f"flap_count={flap_count} ({flap_per_hour:.0f}/hr) exceeds medium threshold {THRESHOLDS['flapping']['medium']}/hr"
        )
    
    return None


def check_path_length(row: Dict[str, Any]) -> Optional[HeuristicHit]:
    """
    Check for unusually long AS paths (possible path inflation or loops).
    """
    path_length = row.get('path_length')
    
    if path_length is None:
        return None
    
    if path_length > THRESHOLDS["path_length"]["severe"]:
        return HeuristicHit(
            rule_name="path_length_severe",
            severity="high",
            score=0.85,
            reason=f"path_length={path_length:.1f} exceeds severe threshold {THRESHOLDS['path_length']['severe']}"
        )
    elif path_length > THRESHOLDS["path_length"]["mild"]:
        return HeuristicHit(
            rule_name="path_length_mild",
            severity="medium",
            score=0.6,
            reason=f"path_length={path_length:.1f} exceeds mild threshold {THRESHOLDS['path_length']['mild']}"
        )
    
    return None


def check_bogon_asn(row: Dict[str, Any]) -> Optional[HeuristicHit]:
    """
    Check for bogon (private use) ASN in origin.
    
    These ASNs should never appear in public BGP routing.
    """
    origin_as = row.get('origin_as')
    
    if origin_as is None:
        return None
    
    # Check if ASN is in any bogon range
    for start, end in BOGON_ASN_RANGES:
        if start <= origin_as <= end:
            return HeuristicHit(
                rule_name="bogon_asn_critical",
                severity="critical",
                score=0.95,
                reason=f"origin_as={origin_as} is in private/reserved range [{start}-{end}] - should not be in public routing"
            )
    
    return None


def check_bogon_prefix(row: Dict[str, Any]) -> Optional[HeuristicHit]:
    """
    Check for bogon (reserved/private) prefixes.
    
    These prefixes should never be routed on the public Internet.
    """
    prefix_str = row.get('prefix')
    
    if not prefix_str:
        return None
    
    try:
        announced_network = ipaddress.ip_network(prefix_str, strict=False)
        
        # Check if announced prefix overlaps with any bogon prefix
        for bogon_str in BOGON_PREFIXES:
            bogon_network = ipaddress.ip_network(bogon_str)
            
            # Check if announced prefix is within or overlaps bogon range
            if announced_network.overlaps(bogon_network):
                return HeuristicHit(
                    rule_name="bogon_prefix_critical",
                    severity="critical",
                    score=0.95,
                    reason=f"prefix={prefix_str} overlaps with bogon range {bogon_str} - reserved/private prefix should not be routed"
                )
    except Exception as e:
        logger.warning(f"Failed to parse prefix {prefix_str}: {e}")
        return None
    
    return None


def check_path_inflation(row: Dict[str, Any], conn: Connection) -> Optional[HeuristicHit]:
    """
    Check for sudden path length increases (path inflation).
    
    Compares current path_length against 7-day baseline for this prefix.
    """
    prefix = row.get('prefix')
    origin_as = row.get('origin_as')
    current_path = row.get('path_length')
    window_start = row.get('window_start')
    
    if not all([prefix, origin_as, current_path, window_start]):
        return None
    
    try:
        # Query 7-day baseline avg path length for this prefix
        cur = conn.cursor()
        cur.execute("""
            SELECT AVG(path_length) as baseline_path
            FROM bgp_features_1min
            WHERE prefix = %s 
            AND origin_as = %s
            AND window_start BETWEEN %s - INTERVAL '7 days' AND %s - INTERVAL '1 hour'
            AND path_length IS NOT NULL
        """, (prefix, origin_as, window_start, window_start))
        
        result = cur.fetchone()
        cur.close()
        
        if result and result[0] is not None:
            baseline_path = float(result[0])
            delta = current_path - baseline_path
            
            if delta > THRESHOLDS["path_inflation"]["critical"]:
                return HeuristicHit(
                    rule_name="path_inflation_critical",
                    severity="critical",
                    score=0.95,
                    reason=f"path_length={current_path:.1f}, baseline={baseline_path:.1f}, delta={delta:.1f} (>10 hop increase) - possible path poisoning"
                )
            elif delta > THRESHOLDS["path_inflation"]["high"]:
                return HeuristicHit(
                    rule_name="path_inflation_high",
                    severity="high",
                    score=0.8,
                    reason=f"path_length={current_path:.1f}, baseline={baseline_path:.1f}, delta={delta:.1f} (>5 hop increase) - suspicious path change"
                )
    except Exception as e:
        logger.warning(f"Failed to check path inflation for {prefix}: {e}")
    
    return None


def check_volume_spike(row: Dict[str, Any]) -> Optional[HeuristicHit]:
    """
    Check for volume spikes (high message rate).
    
    Volume spike indicates potential DDoS, route leak, or infrastructure stress.
    message_rate is already in messages per minute from aggregation.
    """
    message_rate = row.get('message_rate', 0.0)
    
    if message_rate > THRESHOLDS["volume_spike"]["critical"]:
        return HeuristicHit(
            rule_name="volume_spike_critical",
            severity="critical",
            score=0.95,
            reason=f"message_rate={message_rate:.0f} msg/min exceeds critical threshold {THRESHOLDS['volume_spike']['critical']} - severe overload"
        )
    elif message_rate > THRESHOLDS["volume_spike"]["high"]:
        return HeuristicHit(
            rule_name="volume_spike_high",
            severity="high",
            score=0.85,
            reason=f"message_rate={message_rate:.0f} msg/min exceeds high threshold {THRESHOLDS['volume_spike']['high']} - may stress devices"
        )
    
    return None


def check_session_resets(row: Dict[str, Any]) -> Optional[HeuristicHit]:
    """
    Check for BGP session resets (BMP monitoring).
    
    High session reset counts indicate peer instability or DoS attacks.
    """
    session_resets = row.get('session_resets', 0)
    
    if session_resets > THRESHOLDS["session_resets"]["critical"]:
        return HeuristicHit(
            rule_name="session_resets_critical",
            severity="critical",
            score=0.95,
            reason=f"session_resets={session_resets} exceeds critical threshold {THRESHOLDS['session_resets']['critical']} - DoS-level issue"
        )
    elif session_resets >= THRESHOLDS["session_resets"]["high"]:
        return HeuristicHit(
            rule_name="session_resets_high",
            severity="high",
            score=0.85,
            reason=f"session_resets={session_resets} exceeds high threshold {THRESHOLDS['session_resets']['high']} - persistent instability"
        )
    elif session_resets >= THRESHOLDS["session_resets"]["medium"]:
        return HeuristicHit(
            rule_name="session_resets_medium",
            severity="medium",
            score=0.6,
            reason=f"session_resets={session_resets} exceeds medium threshold {THRESHOLDS['session_resets']['medium']} - investigate"
        )
    
    return None


def apply_heuristics(row: Dict[str, Any], conn: Connection) -> List[HeuristicHit]:
    """Apply all heuristic rules to a feature row"""
    hits = []
    
    # Run all checks (9 rules total)
    checks = [
        check_churn(row),
        check_withdrawal_ratio(row),
        check_flapping(row),
        check_path_length(row),
        check_bogon_asn(row),           # Phase 2: Bogon ASN detection
        check_bogon_prefix(row),        # Phase 2: Bogon prefix detection
        check_path_inflation(row, conn),# Phase 2: Path inflation detection
        check_volume_spike(row),        # Phase 3: Volume spike detection
        check_session_resets(row)       # Phase 3: Session reset detection
    ]
    
    # Filter out None results
    hits = [hit for hit in checks if hit is not None]
    
    return hits


def generate_detection_id(window_start: datetime, prefix: str, origin_as: int) -> str:
    """Generate unique detection ID using SHA256"""
    data = f"heuristic_{window_start.isoformat()}_{prefix}_{origin_as}"
    return f"heur_{hashlib.sha256(data.encode()).hexdigest()[:32]}"


def get_prefix_length(prefix_str: str) -> int:
    """Extract prefix length from CIDR notation"""
    try:
        network = ipaddress.ip_network(prefix_str, strict=False)
        return network.prefixlen
    except:
        # Default to /32 for IPv4, /128 for IPv6
        return 32 if ':' not in prefix_str else 128


def determine_classification(hits: List[HeuristicHit]) -> str:
    """Determine classification based on triggered rules"""
    if len(hits) > 1:
        return "multi_rule"
    
    hit = hits[0]
    if "churn" in hit.rule_name:
        return "churn_spike"
    elif "withdrawal" in hit.rule_name:
        return "withdrawal_burst"
    elif "flap" in hit.rule_name:
        return "route_flap"
    elif "path_length" in hit.rule_name:
        return "path_anomaly"
    elif "path_inflation" in hit.rule_name:
        return "path_inflation"
    elif "bogon_asn" in hit.rule_name:
        return "bogon_asn"
    elif "bogon_prefix" in hit.rule_name:
        return "bogon_prefix"
    elif "volume_spike" in hit.rule_name:
        return "volume_spike"
    elif "session_resets" in hit.rule_name:
        return "session_instability"
    else:
        return "unknown"


def get_max_severity(hits: List[HeuristicHit]) -> str:
    """Get highest severity among hits (critical > high > medium > low)"""
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    max_sev = max(hits, key=lambda h: severity_order.get(h.severity, 0))
    return max_sev.severity


def fetch_new_feature_rows(conn: Connection, last_ts: datetime) -> pd.DataFrame:
    """Fetch new feature rows since last_ts"""
    query = """
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
    
    df = pd.read_sql_query(query, conn, params=(last_ts,))
    
    # Convert prefix to string
    if not df.empty:
        df['prefix'] = df['prefix'].astype(str)
    
    return df


def insert_detection(conn: Connection, detection: Dict[str, Any]) -> None:
    """Insert detection into hybrid_anomaly_detections table"""
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO hybrid_anomaly_detections (
                timestamp, detection_id, prefix, prefix_length,
                peer_ip, peer_asn, origin_as, as_path, next_hop,
                event_type, message_type, rpki_status, rpki_anomaly,
                combined_anomaly, combined_score, combined_severity,
                classification, metadata
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (detection_id) DO UPDATE SET
                combined_score = EXCLUDED.combined_score,
                combined_anomaly = EXCLUDED.combined_anomaly,
                combined_severity = EXCLUDED.combined_severity,
                metadata = EXCLUDED.metadata,
                timestamp = EXCLUDED.timestamp
        """, (
            detection['timestamp'],
            detection['detection_id'],
            detection['prefix'],
            detection['prefix_length'],
            detection['peer_ip'],
            detection['peer_asn'],
            detection['origin_as'],
            detection['as_path'],
            detection['next_hop'],
            detection['event_type'],
            detection['message_type'],
            detection['rpki_status'],
            detection['rpki_anomaly'],
            detection['combined_anomaly'],
            detection['combined_score'],
            detection['combined_severity'],
            detection['classification'],
            psycopg.types.json.Jsonb(detection['metadata'])
        ))
    except Exception as e:
        logger.error(f"Failed to insert detection {detection['detection_id']}: {e}")
    finally:
        cur.close()


def process_feature_rows(conn: Connection, df: pd.DataFrame) -> int:
    """Process feature rows and insert detections"""
    detection_count = 0
    
    for idx, row in df.iterrows():
        # Convert row to dict
        row_dict = row.to_dict()
        
        # Apply heuristics (pass conn for path_inflation check)
        hits = apply_heuristics(row_dict, conn)
        
        # Skip if no rules triggered
        if not hits:
            continue
        
        # Calculate combined metrics
        heuristic_score = max(hit.score for hit in hits)
        severity = get_max_severity(hits)
        classification = determine_classification(hits)
        
        # Build metadata
        metadata = {
            "triggered_rules": [
                {
                    "rule_name": hit.rule_name,
                    "severity": hit.severity,
                    "score": hit.score,
                    "reason": hit.reason
                }
                for hit in hits
            ],
            "raw_features": {
                "announcements": int(row_dict['announcements']),
                "withdrawals": int(row_dict['withdrawals']),
                "total_updates": int(row_dict['total_updates']),
                "withdrawal_ratio": float(row_dict['withdrawal_ratio']),
                "flap_count": int(row_dict['flap_count']),
                "path_length": float(row_dict['path_length']) if row_dict['path_length'] is not None else None,
                "unique_peers": int(row_dict['unique_peers']),
                "message_rate": float(row_dict['message_rate']),
                "session_resets": int(row_dict['session_resets'])
            },
            "heuristic_score": heuristic_score,
            "detector_type": "HeuristicDetector",
            "version": VERSION
        }
        
        # Build detection record
        detection = {
            "timestamp": row_dict['window_start'],
            "detection_id": generate_detection_id(
                row_dict['window_start'],
                row_dict['prefix'],
                row_dict['origin_as']
            ),
            "prefix": row_dict['prefix'],
            "prefix_length": get_prefix_length(row_dict['prefix']),
            "peer_ip": None,
            "peer_asn": None,
            "origin_as": int(row_dict['origin_as']),
            "as_path": None,
            "next_hop": None,
            "event_type": "heuristic",
            "message_type": "bgp_features_1min",
            "rpki_status": "unknown",
            "rpki_anomaly": False,
            "combined_anomaly": severity in ["medium", "high", "critical"],
            "combined_score": heuristic_score,
            "combined_severity": severity,
            "classification": classification,
            "metadata": metadata
        }
        
        # Insert detection
        insert_detection(conn, detection)
        detection_count += 1
    
    return detection_count


def main():
    """Main service loop"""
    logger.info("="*60)
    logger.info("Starting Heuristic Detector Service")
    logger.info("="*60)
    logger.info(f"Poll interval: {POLL_INTERVAL}s")
    logger.info(f"Version: {VERSION}")
    logger.info("")
    logger.info("Data-driven thresholds:")
    logger.info(f"  Churn: {THRESHOLDS['churn']}")
    logger.info(f"  Flapping: {THRESHOLDS['flapping']}")
    logger.info(f"  Path length: {THRESHOLDS['path_length']}")
    logger.info("="*60)
    
    # Connect to database
    dsn = build_dsn()
    try:
        conn = get_db_connection(dsn)
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
    
    # Main loop
    iteration = 0
    while True:
        iteration += 1
        logger.info(f"\n--- Iteration {iteration} ---")
        
        try:
            # Get last processed timestamp
            last_ts = get_last_processed_timestamp(conn)
            logger.info(f"Last processed: {last_ts}")
            
            # Fetch new feature rows
            df = fetch_new_feature_rows(conn, last_ts)
            
            if df.empty:
                logger.info("No new feature rows to process")
            else:
                logger.info(f"Fetched {len(df)} new feature rows")
                
                # Process and insert detections
                detection_count = process_feature_rows(conn, df)
                logger.info(f"[OK] Inserted {detection_count} heuristic detections")
                
                # Update state with latest window_start
                latest_window = df['window_start'].max()
                update_state(conn, latest_window, len(df))
                logger.info(f"[OK] Updated state: last_processed = {latest_window}")
        
        except Exception as e:
            logger.error(f"Error in processing loop: {e}", exc_info=True)
        
        # Sleep
        logger.info(f"Sleeping for {POLL_INTERVAL} seconds...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
