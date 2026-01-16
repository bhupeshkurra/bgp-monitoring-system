#!/usr/bin/env python3
"""
ris_live_collector - RIPE RIS Live WebSocket to PostgreSQL BGP collector
Connects to RIPE RIS Live, receives BGP UPDATE messages, and stores them in PostgreSQL.
"""

from __future__ import annotations

import os
import sys
import json
import time
import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

import websocket
from websocket import WebSocketConnectionClosedException
import psycopg
from psycopg import Connection, Cursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Constants
WS_URL = "wss://ris-live.ripe.net/v1/ws/?client=bgp-ensemble"
RECONNECT_DELAY = 5  # seconds


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


def connect_ws() -> websocket.WebSocket:
    """
    Connect to RIPE RIS Live WebSocket.
    
    Returns:
        WebSocket connection object
    """
    logger.info(f"Connecting to RIS Live WebSocket: {WS_URL}")
    ws = websocket.create_connection(WS_URL)
    logger.info("WebSocket connection established")
    return ws


def subscribe(ws: websocket.WebSocket) -> None:
    """
    Send subscription message to RIS Live WebSocket.
    
    Args:
        ws: WebSocket connection
    """
    subscription = {
        "type": "ris_subscribe",
        "data": {
            "type": "UPDATE"
        }
    }
    ws.send(json.dumps(subscription))
    logger.info("Subscription message sent to RIS Live (subscribing to all UPDATEs)")


def is_ipv4_address(addr: str) -> bool:
    """
    Detect if an address string represents IPv4 (vs IPv6).
    
    Simple heuristic: IPv6 addresses contain colons.
    
    Args:
        addr: IP address string
        
    Returns:
        True if IPv4, False if IPv6 or unknown
    """
    return ":" not in addr


def deterministic_peer_uuid(peer: str, peer_asn: int) -> uuid.UUID:
    """
    Generate a deterministic UUID for a BGP peer based on its address and ASN.
    
    Uses SHA1(peer|peer_asn) truncated to 32 hex characters to create a stable
    UUID that will always be the same for a given (peer, peer_asn) pair.
    
    Args:
        peer: Peer IP address string (IPv4 or IPv6)
        peer_asn: Peer AS number
        
    Returns:
        Deterministic UUID suitable as a stable peer identifier
        
    Example:
        >>> deterministic_peer_uuid("185.1.2.3", 65000)
        UUID('a1b2c3d4-e5f6-...')  # Always the same for this peer/ASN
    """
    peer_key = f"{peer}|{peer_asn}"
    hash_digest = hashlib.sha1(peer_key.encode('utf-8')).hexdigest()
    # Take first 32 hex chars and format as UUID
    return uuid.UUID(hash_digest[:32])


def get_peer_hash_id(conn: Connection, peer: str, peer_asn: int) -> uuid.UUID:
    """
    Get or create a stable hash_id for a BGP peer in the bgp_peers table.
    
    This function implements an idempotent upsert pattern:
    1. Generate deterministic UUID from (peer, peer_asn)
    2. Check if peer already exists in bgp_peers
    3. If not, insert minimal OpenBMP-compatible row
    4. Return the stable hash_id
    
    The same peer will always get the same hash_id across service restarts,
    enabling consistent peer tracking and aggregation.
    
    Args:
        conn: Active psycopg Connection with autocommit mode
        peer: Peer IP address (IPv4 or IPv6) as string
        peer_asn: Peer AS number (non-negative integer)
        
    Returns:
        Deterministic UUID (hash_id) identifying this peer
        
    Raises:
        psycopg.Error: On database errors other than unique violations
        
    Note:
        Uses OpenBMP bgp_peers schema with columns:
        hash_id, router_hash_id, peer_rd, isipv4, peer_addr, peer_as, state
    """
    # Generate deterministic hash_id
    hash_id = deterministic_peer_uuid(peer, peer_asn)
    
    # Check if peer already exists
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM public.bgp_peers WHERE hash_id = %s",
            (hash_id,)
        )
        if cur.fetchone():
            return hash_id
    
    # Insert new peer with minimal required OpenBMP fields
    isipv4 = is_ipv4_address(peer)
    router_hash_id = uuid.uuid4()  # Placeholder router ID
    
    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO public.bgp_peers (
                    hash_id,
                    router_hash_id,
                    peer_rd,
                    isipv4,
                    peer_addr,
                    peer_as,
                    state
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (hash_id, router_hash_id, "", isipv4, peer, peer_asn, "up")
            )
            # Note: autocommit is enabled on connection, no explicit commit needed
            logger.debug(f"Registered new peer: {peer} AS{peer_asn} (hash_id={hash_id})")
        except psycopg.errors.UniqueViolation:
            # Race condition: another process inserted this peer
            logger.debug(f"Peer already exists (race): {peer} AS{peer_asn}")
    
    return hash_id


def extract_peer_info(data: Dict[str, Any]) -> tuple[str, int]:
    """
    Extract peer address and ASN from RIS Live UPDATE message.
    
    Provides safe defaults if fields are missing:
    - peer defaults to "0.0.0.0" (unknown IPv4)
    - peer_asn defaults to 0 (unknown ASN)
    
    Args:
        data: Parsed RIS Live BGP UPDATE message
        
    Returns:
        Tuple of (peer_addr, peer_asn)
    """
    peer = data.get("peer", "0.0.0.0")
    peer_asn = data.get("peer_asn", 0)
    
    # Ensure peer_asn is an integer
    if not isinstance(peer_asn, int):
        try:
            peer_asn = int(peer_asn)
        except (ValueError, TypeError):
            peer_asn = 0
    
    return peer, peer_asn


def get_or_create_base_attrs(conn: Connection, peer_hash_id: uuid.UUID, 
                              as_path: Optional[list], origin_as: int,
                              next_hop: Optional[str]) -> uuid.UUID:
    """
    Get or create base_attrs entry for BGP path attributes.
    
    Generates a deterministic hash of the path attributes and either returns
    the existing hash_id or creates a new base_attrs entry.
    
    Args:
        conn: Database connection
        peer_hash_id: Peer identifier
        as_path: AS_PATH as list of AS numbers (e.g., [65000, 65001, 174])
        origin_as: Origin AS number
        next_hop: Next hop IP address (may contain comma-separated IPs)
        
    Returns:
        UUID hash_id for the base_attrs entry
    """
    # Handle missing AS path
    if not as_path or len(as_path) == 0:
        as_path = [origin_as] if origin_as else []
    
    # Ensure origin_as is at the end of path if not present
    if origin_as and (not as_path or as_path[-1] != origin_as):
        as_path = list(as_path) + [origin_as]
    
    # Handle multiple next_hop addresses (comma-separated) - take first only
    if next_hop and ',' in next_hop:
        next_hop = next_hop.split(',')[0].strip()
    
    # Create deterministic hash of attributes
    attr_string = f"{as_path}|{origin_as}|{next_hop or ''}"
    hash_digest = hashlib.sha1(attr_string.encode('utf-8')).hexdigest()
    hash_id = uuid.UUID(hash_digest[:32])
    
    # Check if already exists
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM public.base_attrs WHERE hash_id = %s", (hash_id,))
        if cur.fetchone():
            return hash_id
    
    # Insert new base_attrs entry
    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO public.base_attrs (
                    hash_id, peer_hash_id, origin, as_path, as_path_count,
                    origin_as, next_hop, timestamp, nexthop_isipv4
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    hash_id,
                    peer_hash_id,
                    'IGP',  # Default origin
                    as_path,
                    len(as_path),
                    origin_as,
                    next_hop,
                    datetime.now(timezone.utc).replace(tzinfo=None),
                    is_ipv4_address(next_hop) if next_hop else True
                )
            )
            logger.debug(f"Created base_attrs: path_len={len(as_path)}, origin_as={origin_as}")
        except psycopg.errors.UniqueViolation:
            # Race condition: another process created it
            logger.debug(f"base_attrs already exists (race): {hash_id}")
    
    return hash_id


def handle_update(cur: Cursor, data: Dict[str, Any]) -> None:
    """
    Process a BGP UPDATE message from RIS Live and insert into ip_rib table.
    
    Handles both announcements and withdrawals. For each prefix:
    - Extracts peer information and generates stable peer hash_id
    - Parses prefix and determines IPv4/IPv6
    - Inserts row into ip_rib with appropriate fields
    
    Args:
        cur: Active database cursor
        data: Parsed RIS Live BGP UPDATE message (JSON dict)
        
    Returns:
        None
        
    Note:
        Errors are logged but don't stop processing of other prefixes
        in the same message.
    """
    # Extract and validate timestamp
    timestamp_unix = data.get("timestamp")
    if timestamp_unix is None:
        logger.warning("Skipping UPDATE message: missing timestamp")
        return
    
    # Convert UNIX timestamp to naive UTC datetime
    dt = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc).replace(tzinfo=None)
    
    # Extract peer information with safe defaults
    peer, peer_asn = extract_peer_info(data)
    
    # Get or create stable peer identifier in bgp_peers table
    peer_hash_id = get_peer_hash_id(cur.connection, peer, peer_asn)
    
    # Extract AS_PATH from top-level data (shared by all announcements in this UPDATE)
    as_path_from_data = data.get("path", [])
    
    # Process announcements
    announcements = data.get("announcements", [])
    for announcement in announcements:
        try:
            prefix = announcement.get("prefixes") or announcement.get("prefix")
            if isinstance(prefix, list):
                prefixes = prefix
            elif isinstance(prefix, str):
                prefixes = [prefix]
            else:
                continue
            
            for pfx in prefixes:
                if "/" not in pfx:
                    continue
                
                prefix_str, prefix_len_str = pfx.rsplit("/", 1)
                prefix_len = int(prefix_len_str)
                
                # Determine if IPv4
                isipv4 = ":" not in pfx
                
                # Use AS_PATH from data level (not per-announcement)
                as_path = as_path_from_data
                
                # Origin AS is the last AS in the path, or peer_asn as fallback
                origin_as = as_path[-1] if as_path else peer_asn
                
                # Extract next hop from announcement
                next_hop = announcement.get("next_hop")
                
                # Get or create base_attrs with AS path information
                base_attr_hash_id = get_or_create_base_attrs(
                    cur.connection, peer_hash_id, as_path, origin_as, next_hop
                )
                
                # Generate hash_id for this rib entry
                hash_id = uuid.uuid4()
                
                # Insert into database
                insert_query = """
                    INSERT INTO public.ip_rib (
                        hash_id, base_attr_hash_id, peer_hash_id, isipv4,
                        origin_as, prefix, prefix_len, timestamp, first_added_timestamp,
                        iswithdrawn, path_id, labels
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """
                
                cur.execute(insert_query, (
                    hash_id,
                    base_attr_hash_id,
                    peer_hash_id,
                    isipv4,
                    origin_as,
                    pfx,
                    prefix_len,
                    dt,
                    dt,  # first_added_timestamp == timestamp
                    False,  # iswithdrawn
                    0,  # path_id
                    None  # labels
                ))
                
                logger.debug(f"Inserted announcement: {pfx} from AS{peer_asn}")
        
        except Exception as e:
            logger.error(f"Error processing announcement: {e}", exc_info=True)
    
    # Process withdrawals
    withdrawals = data.get("withdrawals", [])
    for withdrawal in withdrawals:
        try:
            # Withdrawals can be a string or dict with prefix field
            if isinstance(withdrawal, str):
                pfx = withdrawal
            elif isinstance(withdrawal, dict):
                pfx = withdrawal.get("prefix")
            else:
                continue
            
            if not pfx or "/" not in pfx:
                continue
            
            prefix_str, prefix_len_str = pfx.rsplit("/", 1)
            prefix_len = int(prefix_len_str)
            
            # Determine if IPv4
            isipv4 = ":" not in pfx
            
            # For withdrawals, we don't have path info, use placeholder base_attrs
            # with just the peer_asn as the path
            base_attr_hash_id = get_or_create_base_attrs(
                cur.connection, peer_hash_id, [peer_asn], peer_asn, None
            )
            
            # Generate hash_id for this rib entry
            hash_id = uuid.uuid4()
            
            # Insert into database
            insert_query = """
                INSERT INTO public.ip_rib (
                    hash_id, base_attr_hash_id, peer_hash_id, isipv4,
                    origin_as, prefix, prefix_len, timestamp, first_added_timestamp,
                    iswithdrawn, path_id, labels
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """
            
            cur.execute(insert_query, (
                hash_id,
                base_attr_hash_id,
                peer_hash_id,
                isipv4,
                peer_asn,  # origin_as
                pfx,
                prefix_len,
                dt,
                dt,  # first_added_timestamp == timestamp
                True,  # iswithdrawn
                0,  # path_id
                None  # labels
            ))
            
            logger.debug(f"Inserted withdrawal: {pfx} from AS{peer_asn}")
        
        except Exception as e:
            logger.error(f"Error processing withdrawal: {e}", exc_info=True)


def main():
    """
    Main service loop: connect to database and WebSocket, process messages.
    """
    logger.info("Starting ris_live_collector service...")
    
    # Connect to database
    dsn = build_dsn()
    try:
        conn = connect_db(dsn)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}", exc_info=True)
        sys.exit(1)
    
    # Main reconnection loop
    while True:
        ws: Optional[websocket.WebSocket] = None
        try:
            # Connect to WebSocket
            ws = connect_ws()
            subscribe(ws)
            
            # Message processing loop
            message_count = 0
            while True:
                try:
                    raw_message = ws.recv()
                    
                    # Handle empty or whitespace-only frames
                    if not raw_message or not raw_message.strip():
                        continue
                    
                    try:
                        message = json.loads(raw_message)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON message: {e}")
                        time.sleep(0.1)
                        continue
                    
                    # Only process ris_message types
                    if message.get("type") != "ris_message":
                        continue
                    
                    data = message.get("data", {})
                    
                    # Only handle UPDATE messages
                    if data.get("type") != "UPDATE":
                        continue
                    
                    # Process the UPDATE
                    with conn.cursor() as cur:
                        handle_update(cur, data)
                    
                    message_count += 1
                    if message_count % 100 == 0:
                        logger.info(f"Processed {message_count} UPDATE messages")
                
                except WebSocketConnectionClosedException:
                    logger.warning("WebSocket closed by server, will reconnect")
                    break
                
                except psycopg.Error as e:
                    logger.error(f"Database error: {e}", exc_info=True)
                    # Continue processing even if one insert fails
                    continue
        
        except websocket.WebSocketException as e:
            logger.error(f"WebSocket error: {e}", exc_info=True)
        
        except KeyboardInterrupt:
            logger.info("Received shutdown signal, exiting...")
            if ws:
                ws.close()
            conn.close()
            sys.exit(0)
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
        
        finally:
            # Close WebSocket if it's open
            if ws:
                try:
                    ws.close()
                except:
                    pass
        
        # Wait before reconnecting
        logger.info(f"Reconnecting in {RECONNECT_DELAY} seconds...")
        time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    main()
