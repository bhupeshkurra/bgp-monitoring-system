-- BGP Monitoring System - Database Schema
-- PostgreSQL 13+ required
-- Database: bgp_ensemble_db

-- =============================================================================
-- CORE BGP TABLES
-- =============================================================================

-- IP RIB (Routing Information Base) - Stores IPv4/IPv6 BGP routes
CREATE TABLE IF NOT EXISTS ip_rib (
    hash_id UUID NOT NULL,
    base_attr_hash_id UUID,
    peer_hash_id UUID NOT NULL,
    isipv4 BOOLEAN NOT NULL,
    origin_as BIGINT,
    prefix INET NOT NULL,
    prefix_len SMALLINT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    first_added_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    iswithdrawn BOOLEAN NOT NULL DEFAULT false,
    path_id BIGINT,
    labels VARCHAR(255),
    isprepolicy BOOLEAN NOT NULL DEFAULT true,
    isadjribin BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_ip_rib_peer_hash ON ip_rib(peer_hash_id);
CREATE INDEX IF NOT EXISTS idx_ip_rib_peer_time ON ip_rib(peer_hash_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_ip_rib_prefix ON ip_rib(prefix);
CREATE INDEX IF NOT EXISTS idx_ip_rib_timestamp ON ip_rib(timestamp DESC);

-- L3VPN RIB - Stores L3VPN BGP routes
CREATE TABLE IF NOT EXISTS l3vpn_rib (
    hash_id UUID NOT NULL,
    base_attr_hash_id UUID,
    peer_hash_id UUID NOT NULL,
    rd_administrator VARCHAR(50),
    rd_assigned_number BIGINT,
    rd_type SMALLINT,
    origin_as BIGINT,
    prefix INET NOT NULL,
    prefix_len SMALLINT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    first_added_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    iswithdrawn BOOLEAN NOT NULL DEFAULT false,
    path_id BIGINT,
    labels VARCHAR(255),
    isprepolicy BOOLEAN NOT NULL DEFAULT true,
    isadjribin BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_l3vpn_rib_peer_hash ON l3vpn_rib(peer_hash_id);
CREATE INDEX IF NOT EXISTS idx_l3vpn_rib_timestamp ON l3vpn_rib(timestamp DESC);

-- BGP Peers - Stores peer information
CREATE TABLE IF NOT EXISTS bgp_peers (
    hash_id UUID PRIMARY KEY,
    router_hash_id UUID,
    peer_rd VARCHAR(32),
    isipv4 BOOLEAN,
    peer_addr INET,
    name VARCHAR(200),
    peer_bgp_id INET,
    peer_as BIGINT,
    state VARCHAR(20),
    isL3VPNpeer BOOLEAN,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    isprepolicy BOOLEAN DEFAULT true,
    isadjribin BOOLEAN DEFAULT true,
    geo_ip_start INET
);

-- =============================================================================
-- FEATURE ENGINEERING TABLES
-- =============================================================================

-- BGP Features (1-minute aggregation)
CREATE TABLE IF NOT EXISTS bgp_features_1min (
    id BIGSERIAL PRIMARY KEY,
    window_start TIMESTAMP WITH TIME ZONE NOT NULL,
    window_end TIMESTAMP WITH TIME ZONE NOT NULL,
    prefix INET NOT NULL,
    origin_as BIGINT NOT NULL,
    announcements INTEGER NOT NULL,
    withdrawals INTEGER NOT NULL,
    total_updates INTEGER NOT NULL,
    withdrawal_ratio DOUBLE PRECISION NOT NULL,
    flap_count INTEGER NOT NULL,
    path_length DOUBLE PRECISION,
    unique_peers INTEGER NOT NULL,
    message_rate DOUBLE PRECISION NOT NULL,
    session_resets INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bgp_features_1min_window_start ON bgp_features_1min(window_start);

-- =============================================================================
-- RPKI VALIDATION
-- =============================================================================

-- RPKI Validator - Stores ROAs (Route Origin Authorizations)
CREATE TABLE IF NOT EXISTS rpki_validator (
    prefix INET NOT NULL,
    prefix_len SMALLINT NOT NULL DEFAULT 0,
    prefix_len_max SMALLINT NOT NULL DEFAULT 0,
    origin_as BIGINT NOT NULL,
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

-- =============================================================================
-- ANOMALY DETECTION RESULTS
-- =============================================================================

-- Hybrid Anomaly Detections - Combined ML + Heuristic + RPKI detections
CREATE TABLE IF NOT EXISTS hybrid_anomaly_detections (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    detection_id VARCHAR(100) UNIQUE,
    prefix VARCHAR(45),
    prefix_length INTEGER,
    peer_ip VARCHAR(45),
    peer_asn BIGINT,
    origin_as BIGINT,
    as_path TEXT,
    next_hop VARCHAR(45),
    event_type VARCHAR(20),
    message_type VARCHAR(50),
    rpki_status VARCHAR(20),
    rpki_anomaly BOOLEAN DEFAULT false,
    combined_anomaly BOOLEAN DEFAULT false,
    combined_score NUMERIC(10,4),
    combined_severity VARCHAR(20),
    classification VARCHAR(50),
    metadata JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS hybrid_anomaly_detections_detection_id_key ON hybrid_anomaly_detections(detection_id);

-- Correlated Detections - Multi-signal correlation results
CREATE TABLE IF NOT EXISTS correlated_detections (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    prefix VARCHAR(45),
    origin_as BIGINT,
    detection_window_start TIMESTAMP WITHOUT TIME ZONE,
    detection_window_end TIMESTAMP WITHOUT TIME ZONE,
    classification VARCHAR(50),
    final_severity VARCHAR(20),
    confidence_score NUMERIC(10,4),
    source_count INTEGER,
    heuristic_signals JSONB,
    ml_signals JSONB,
    rpki_signals JSONB,
    combined_metadata JSONB,
    alert_sent BOOLEAN DEFAULT false
);

-- =============================================================================
-- SERVICE STATE TABLES
-- =============================================================================

-- Feature Aggregator State
CREATE TABLE IF NOT EXISTS feature_aggregator_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_processed_timestamp TIMESTAMP WITH TIME ZONE
);

-- ML Inference State
CREATE TABLE IF NOT EXISTS ml_inference_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_processed_timestamp TIMESTAMP WITH TIME ZONE,
    total_processed BIGINT DEFAULT 0,
    last_update TIMESTAMP WITH TIME ZONE DEFAULT now(),
    CONSTRAINT ml_inference_state_id_check CHECK (id = 1)
);

-- Heuristic Inference State
CREATE TABLE IF NOT EXISTS heuristic_inference_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_processed_timestamp TIMESTAMP WITH TIME ZONE
);

-- RPKI Inference State
CREATE TABLE IF NOT EXISTS rpki_inference_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_processed_timestamp TIMESTAMP WITH TIME ZONE
);

-- Correlation Engine State
CREATE TABLE IF NOT EXISTS correlation_engine_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_processed_timestamp TIMESTAMP WITH TIME ZONE
);

-- Initialize state tables
INSERT INTO feature_aggregator_state (id, last_processed_timestamp) 
VALUES (1, now() - interval '1 hour')
ON CONFLICT (id) DO NOTHING;

INSERT INTO ml_inference_state (id, last_processed_timestamp, total_processed) 
VALUES (1, now() - interval '1 hour', 0)
ON CONFLICT (id) DO NOTHING;

INSERT INTO heuristic_inference_state (id, last_processed_timestamp) 
VALUES (1, now() - interval '1 hour')
ON CONFLICT (id) DO NOTHING;

INSERT INTO rpki_inference_state (id, last_processed_timestamp) 
VALUES (1, now() - interval '1 hour')
ON CONFLICT (id) DO NOTHING;

INSERT INTO correlation_engine_state (id, last_processed_timestamp) 
VALUES (1, now() - interval '1 hour')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- OPTIONAL: Enable table optimizations for better performance
-- =============================================================================

ALTER TABLE ip_rib SET (
    autovacuum_analyze_threshold = 100,
    autovacuum_vacuum_threshold = 200,
    autovacuum_vacuum_cost_limit = 200,
    autovacuum_vacuum_cost_delay = 10
);

-- =============================================================================
-- SCHEMA CREATION COMPLETE
-- =============================================================================
