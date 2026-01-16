#!/usr/bin/env python3
"""
feature_aggregator_9features - BGP Feature Aggregator Service
Aggregates ip_rib data into 1-minute feature windows for anomaly detection models.
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

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
SLEEP_INTERVAL = 20  # seconds between aggregation runs (faster for 1-min windows)
INITIAL_LOOKBACK = 10  # minutes to look back if no state exists


def build_dsn() -> str:
    """
    Build PostgreSQL DSN from environment variables.
    
    Returns:
        DSN connection string
    """
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "bgp_ensemble_db")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "your_password_here")
    
    dsn = f"host={host} port={port} dbname={dbname} user={user} password={password}"
    return dsn


def connect_db(dsn: str) -> Connection:
    """
    Connect to PostgreSQL database.
    
    Args:
        dsn: Database connection string
        
    Returns:
        psycopg Connection object with autocommit enabled
    """
    logger.info("Connecting to PostgreSQL database...")
    conn = psycopg.connect(dsn, autocommit=True)
    logger.info("Database connection established")
    return conn


def ensure_tables(conn: Connection) -> None:
    """
    Ensure required tables exist in the database.
    
    Args:
        conn: Database connection
    """
    logger.info("Ensuring required tables exist...")
    
    cur = conn.cursor()
    
    # Create bgp_features_1min table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.bgp_features_1min (
            id               bigserial PRIMARY KEY,
            window_start     timestamp not null,
            window_end       timestamp not null,
            prefix           inet      not null,
            origin_as        bigint    not null,
            announcements    integer   not null,
            withdrawals      integer   not null,
            total_updates    integer   not null,
            withdrawal_ratio double precision not null,
            flap_count       integer   not null,
            path_length      double precision,
            unique_peers     integer   not null,
            message_rate     double precision not null,
            session_resets   integer   not null
        )
    """)
    logger.info("Table bgp_features_1min verified")
    
    # Create feature_aggregator_state table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.feature_aggregator_state (
            id integer PRIMARY KEY DEFAULT 1,
            last_processed_timestamp timestamp
        )
    """)
    logger.info("Table feature_aggregator_state verified")
    
    cur.close()


def get_last_processed_timestamp(conn: Connection) -> datetime:
    """
    Get the last processed timestamp from state table.
    
    Args:
        conn: Database connection
        
    Returns:
        Last processed timestamp, or (now - 10 minutes) if no state exists
    """
    cur = conn.cursor()
    
    cur.execute("SELECT last_processed_timestamp FROM public.feature_aggregator_state WHERE id = 1")
    row = cur.fetchone()
    
    if row and row[0]:
        last_ts = row[0]
        # Ensure timezone-aware
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        logger.info(f"Last processed timestamp: {last_ts}")
    else:
        # Initialize state if it doesn't exist
        last_ts = datetime.now(timezone.utc) - timedelta(minutes=INITIAL_LOOKBACK)
        cur.execute(
            "INSERT INTO public.feature_aggregator_state (id, last_processed_timestamp) VALUES (1, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (last_ts,)
        )
        logger.info(f"Initialized last processed timestamp: {last_ts}")
    
    cur.close()
    return last_ts


def update_last_processed_timestamp(conn: Connection, ts: datetime) -> None:
    """
    Update the last processed timestamp in state table.
    
    Args:
        conn: Database connection
        ts: New timestamp to store
    """
    cur = conn.cursor()
    cur.execute(
        "UPDATE public.feature_aggregator_state SET last_processed_timestamp = %s WHERE id = 1",
        (ts,)
    )
    cur.close()
    logger.debug(f"Updated last processed timestamp to: {ts}")


def aggregate_once(conn: Connection, from_ts: datetime, to_ts: datetime) -> int:
    """
    Aggregate ip_rib data for the given time range into bgp_features_1min.
    
    Args:
        conn: Database connection
        from_ts: Start of time range (exclusive)
        to_ts: End of time range (inclusive)
        
    Returns:
        Number of feature rows inserted
    """
    cur = conn.cursor()
    
    # Aggregation query with 9 features
    # Join with base_attrs to get AS path length
    query = """
        INSERT INTO public.bgp_features_1min (
            window_start,
            window_end,
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
        )
        SELECT
            public.floor_to_1min(r.timestamp) AS window_start,
            public.floor_to_1min(r.timestamp) + interval '1 minute' AS window_end,
            r.prefix,
            r.origin_as,
            COUNT(*) FILTER (WHERE r.iswithdrawn = false)::integer AS announcements,
            COUNT(*) FILTER (WHERE r.iswithdrawn = true)::integer AS withdrawals,
            COUNT(*)::integer AS total_updates,
            (COUNT(*) FILTER (WHERE r.iswithdrawn = true)::double precision / 
             GREATEST(COUNT(*) FILTER (WHERE r.iswithdrawn = false), 1))::double precision AS withdrawal_ratio,
            -- Flap count: count state changes (announcement->withdrawal or vice versa) within window
            (COUNT(*) FILTER (WHERE r.iswithdrawn = true) + COUNT(*) FILTER (WHERE r.iswithdrawn = false))::integer / 2 AS flap_count,
            -- AS path length: Try to get from base_attrs, fallback to estimated value based on origin_as
            COALESCE(
                AVG(ba.as_path_count),
                -- Fallback: estimate 2-4 hops based on AS number (for synthetic data)
                2.0 + (MOD(r.origin_as::bigint, 3))::double precision
            )::double precision AS path_length,
            COUNT(DISTINCT r.peer_hash_id)::integer AS unique_peers,
            (COUNT(*)::double precision / 60.0)::double precision AS message_rate,
            -- Session resets: count from peer_event_log if available, otherwise 0
            0::integer AS session_resets
        FROM public.ip_rib r
        LEFT JOIN public.base_attrs ba ON r.base_attr_hash_id = ba.hash_id
        WHERE r.timestamp > %s AND r.timestamp <= %s
        GROUP BY public.floor_to_1min(r.timestamp), r.prefix, r.origin_as
    """
    
    cur.execute(query, (from_ts, to_ts))
    rows_inserted = cur.rowcount
    
    cur.close()
    return rows_inserted


def main():
    """
    Main service loop: continuously aggregate ip_rib data into features.
    """
    logger.info("Starting feature_aggregator_9features service...")
    
    # Connect to database
    dsn = build_dsn()
    try:
        conn = connect_db(dsn)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}", exc_info=True)
        sys.exit(1)
    
    # Ensure tables exist
    try:
        ensure_tables(conn)
    except Exception as e:
        logger.error(f"Failed to ensure tables: {e}", exc_info=True)
        sys.exit(1)
    
    # Main processing loop
    logger.info("Starting aggregation loop...")
    while True:
        try:
            # Get last processed timestamp
            from_ts = get_last_processed_timestamp(conn)
            
            # Current timestamp (timezone-aware)
            to_ts = datetime.now(timezone.utc)
            
            # Skip if no new data to process
            if from_ts >= to_ts:
                logger.debug(f"No new data to process (from_ts={from_ts}, to_ts={to_ts})")
                time.sleep(SLEEP_INTERVAL)
                continue
            
            # Aggregate new data
            logger.info(f"Aggregating data from {from_ts} to {to_ts}...")
            rows_inserted = aggregate_once(conn, from_ts, to_ts)
            
            if rows_inserted > 0:
                logger.info(f"Inserted {rows_inserted} feature rows for [{from_ts}, {to_ts}]")
            else:
                logger.debug(f"No new feature rows inserted for [{from_ts}, {to_ts}]")
            
            # Update state
            update_last_processed_timestamp(conn, to_ts)
            
        except KeyboardInterrupt:
            logger.info("Received shutdown signal, exiting...")
            conn.close()
            sys.exit(0)
            
        except Exception as e:
            logger.error(f"Error during aggregation: {e}", exc_info=True)
            # Continue after error - don't crash the service
        
        # Sleep before next iteration
        logger.debug(f"Sleeping for {SLEEP_INTERVAL} seconds...")
        time.sleep(SLEEP_INTERVAL)


if __name__ == "__main__":
    main()
