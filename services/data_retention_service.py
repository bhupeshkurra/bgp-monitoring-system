#!/usr/bin/env python3
"""
Data Retention Service - Maintains a rolling 3-day window of BGP data
Automatically deletes data older than 3 days from all tables
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta

import psycopg
from psycopg import Connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Constants
RETENTION_DAYS = 3  # Keep only last 3 days of data
CHECK_INTERVAL = 3600  # Check every hour (3600 seconds)


def build_dsn() -> str:
    """Build PostgreSQL DSN from environment variables."""
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "bgp_ensemble_db")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "your_password_here")
    
    dsn = f"host={host} port={port} dbname={dbname} user={user} password={password}"
    return dsn


def connect_db(dsn: str) -> Connection:
    """Connect to PostgreSQL database."""
    logger.info("Connecting to PostgreSQL database...")
    conn = psycopg.connect(dsn, autocommit=False)
    logger.info("Database connection established")
    return conn


def cleanup_old_data(conn: Connection, retention_days: int) -> dict:
    """
    Delete data older than retention_days from all tables.
    
    Args:
        conn: Database connection
        retention_days: Number of days to retain
        
    Returns:
        Dictionary with counts of deleted rows per table
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=retention_days)
    logger.info(f"Deleting data older than {cutoff_time} (>{retention_days} days old)...")
    
    deleted_counts = {}
    
    try:
        cur = conn.cursor()
        
        # 1. Delete from ip_rib (main BGP messages table)
        logger.info("Cleaning ip_rib table...")
        cur.execute("DELETE FROM public.ip_rib WHERE timestamp < %s", (cutoff_time,))
        deleted_counts['ip_rib'] = cur.rowcount
        logger.info(f"  Deleted {cur.rowcount} rows from ip_rib")
        
        # 2. Delete from bgp_features_1min (aggregated features)
        logger.info("Cleaning bgp_features_1min table...")
        cur.execute("DELETE FROM public.bgp_features_1min WHERE window_start < %s", (cutoff_time,))
        deleted_counts['bgp_features_1min'] = cur.rowcount
        logger.info(f"  Deleted {cur.rowcount} rows from bgp_features_1min")
        
        # 3. Delete from hybrid_anomaly_detections
        logger.info("Cleaning hybrid_anomaly_detections table...")
        cur.execute("DELETE FROM public.hybrid_anomaly_detections WHERE timestamp < %s", (cutoff_time,))
        deleted_counts['hybrid_anomaly_detections'] = cur.rowcount
        logger.info(f"  Deleted {cur.rowcount} rows from hybrid_anomaly_detections")
        
        # 4. Delete from heuristic_anomalies (if exists)
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'heuristic_anomalies'
            )
        """)
        if cur.fetchone()[0]:
            logger.info("Cleaning heuristic_anomalies table...")
            cur.execute("DELETE FROM public.heuristic_anomalies WHERE detected_at < %s", (cutoff_time,))
            deleted_counts['heuristic_anomalies'] = cur.rowcount
            logger.info(f"  Deleted {cur.rowcount} rows from heuristic_anomalies")
        
        # 5. Delete from ml_anomalies (if exists)
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'ml_anomalies'
            )
        """)
        if cur.fetchone()[0]:
            logger.info("Cleaning ml_anomalies table...")
            cur.execute("DELETE FROM public.ml_anomalies WHERE detected_at < %s", (cutoff_time,))
            deleted_counts['ml_anomalies'] = cur.rowcount
            logger.info(f"  Deleted {cur.rowcount} rows from ml_anomalies")
        
        # 6. Delete from rpki_validation_results (if exists)
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'rpki_validation_results'
            )
        """)
        if cur.fetchone()[0]:
            logger.info("Cleaning rpki_validation_results table...")
            cur.execute("DELETE FROM public.rpki_validation_results WHERE validated_at < %s", (cutoff_time,))
            deleted_counts['rpki_validation_results'] = cur.rowcount
            logger.info(f"  Deleted {cur.rowcount} rows from rpki_validation_results")
        
        # Commit all deletions
        conn.commit()
        cur.close()
        
        total_deleted = sum(deleted_counts.values())
        logger.info(f"✓ Cleanup complete: Deleted {total_deleted} total rows across all tables")
        
        return deleted_counts
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        conn.rollback()
        raise


def get_database_stats(conn: Connection) -> dict:
    """Get current database statistics."""
    cur = conn.cursor()
    
    stats = {}
    
    # Get row counts and data ranges
    tables = {
        'ip_rib': 'timestamp',
        'bgp_features_1min': 'window_start',
        'hybrid_anomaly_detections': 'timestamp'
    }
    
    for table, timestamp_col in tables.items():
        try:
            cur.execute(f"""
                SELECT 
                    COUNT(*) as row_count,
                    MIN({timestamp_col}) as earliest,
                    MAX({timestamp_col}) as latest,
                    pg_size_pretty(pg_total_relation_size('public.{table}')) as size
                FROM public.{table}
            """)
            row = cur.fetchone()
            if row:
                stats[table] = {
                    'rows': row[0],
                    'earliest': row[1],
                    'latest': row[2],
                    'size': row[3]
                }
        except Exception as e:
            logger.debug(f"Could not get stats for {table}: {e}")
    
    cur.close()
    return stats


def main():
    """Main service loop: periodically clean up old data."""
    logger.info(f"Starting Data Retention Service (keeping last {RETENTION_DAYS} days)...")
    
    # Connect to database
    dsn = build_dsn()
    try:
        conn = connect_db(dsn)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}", exc_info=True)
        sys.exit(1)
    
    # Main processing loop
    logger.info(f"Starting cleanup loop (checking every {CHECK_INTERVAL} seconds)...")
    
    while True:
        try:
            # Show current stats before cleanup
            logger.info("=" * 60)
            logger.info("Database Statistics BEFORE cleanup:")
            stats = get_database_stats(conn)
            for table, info in stats.items():
                logger.info(f"  {table}:")
                logger.info(f"    Rows: {info['rows']:,}")
                logger.info(f"    Range: {info['earliest']} to {info['latest']}")
                logger.info(f"    Size: {info['size']}")
            
            # Perform cleanup
            deleted = cleanup_old_data(conn, RETENTION_DAYS)
            
            # Show stats after cleanup
            if sum(deleted.values()) > 0:
                logger.info("Database Statistics AFTER cleanup:")
                stats = get_database_stats(conn)
                for table, info in stats.items():
                    logger.info(f"  {table}:")
                    logger.info(f"    Rows: {info['rows']:,}")
                    logger.info(f"    Range: {info['earliest']} to {info['latest']}")
                    logger.info(f"    Size: {info['size']}")
            else:
                logger.info("No old data to delete - database is clean")
            
            logger.info("=" * 60)
            
        except KeyboardInterrupt:
            logger.info("Received shutdown signal, exiting...")
            conn.close()
            sys.exit(0)
            
        except Exception as e:
            logger.error(f"Error during retention check: {e}", exc_info=True)
            # Continue after error - don't crash the service
        
        # Sleep before next check
        logger.info(f"Sleeping for {CHECK_INTERVAL} seconds until next cleanup check...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
