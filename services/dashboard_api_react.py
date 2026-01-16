"""
BGP Monitoring System - React Dashboard API Server
Flask-based REST API with WebSocket support for real-time updates
"""

import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, timezone
import logging
import threading
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app initialization
app = Flask(__name__)
CORS(app)

# Initialize SocketIO with eventlet for async support
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', logger=True, engineio_logger=False)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'bgp_ensemble_db',
    'user': 'postgres',
    'password': 'your_password_here'
}

def get_db_connection():
    """Create and return a database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

# ============================================
# Health & Status Endpoints
# ============================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Check API and database health"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'database': 'connected'
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': str(e)
        }), 500

# ============================================
# Dashboard Widget Endpoints
# ============================================

@app.route('/api/dashboard/churn', methods=['GET'])
def get_dashboard_churn():
    """Get churn data for dashboard widget"""
    try:
        time_range = request.args.get('time_range', '24h')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get time series data
        cursor.execute("""
            SELECT window_start as time, 
                   SUM(announcements) as announcements,
                   SUM(withdrawals) as withdrawals
            FROM bgp_features_1min
            WHERE window_start > NOW() - INTERVAL %s
            GROUP BY window_start
            ORDER BY window_start ASC
            LIMIT 60
        """, (time_range,))
        
        time_series = [{'time': row['time'].isoformat(), 
                       'announcements': int(row['announcements'] or 0), 
                       'withdrawals': int(row['withdrawals'] or 0)} 
                      for row in cursor.fetchall()]
        
        # Get top churning prefixes
        cursor.execute("""
            SELECT prefix, 
                   SUM(announcements + withdrawals) as total_churn
            FROM bgp_features_1min
            WHERE window_start > NOW() - INTERVAL %s
            GROUP BY prefix
            ORDER BY total_churn DESC
            LIMIT 5
        """, (time_range,))
        
        top_prefixes = []
        for row in cursor.fetchall():
            total = int(row['total_churn'] or 0)
            severity = 'critical' if total > 1000 else ('high' if total > 500 else 'medium')
            top_prefixes.append({
                'prefix': row['prefix'], 
                'count': total, 
                'severity': severity
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'timeSeries': time_series,
            'topPrefixes': top_prefixes
        })
    except Exception as e:
        logger.error(f"Error in dashboard/churn: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard/anomalies', methods=['GET'])
def get_dashboard_anomalies():
    """Get active anomalies for dashboard widget"""
    try:
        time_range = request.args.get('time_range', '24h')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query anomalies
        cursor.execute("""
            SELECT id, timestamp, detection_id, prefix, origin_as, 
                   classification, combined_severity, combined_score, 
                   rpki_status, metadata, event_type
            FROM hybrid_anomaly_detections
            WHERE timestamp > NOW() - INTERVAL %s
                AND classification IS NOT NULL
                AND classification != 'NORMAL'
            ORDER BY combined_score DESC NULLS LAST, timestamp DESC
            LIMIT 100
        """, (time_range,))
        
        rows = cursor.fetchall()
        anomalies = []
        
        for row in rows:
            rca = 'No details available'
            anomaly_name = row['classification']  # Default to classification
            
            if row['metadata'] and isinstance(row['metadata'], dict):
                rca = row['metadata'].get('rca', 'No details available')
                
                # Extract specific anomaly name from triggered_rules
                triggered_rules = row['metadata'].get('triggered_rules', [])
                if triggered_rules and len(triggered_rules) > 0:
                    # Use the first (or highest severity) rule name
                    anomaly_name = triggered_rules[0].get('rule_name', row['classification'])
                elif row['event_type'] == 'rpki':
                    # For RPKI, use description or status
                    rpki_desc = row['metadata'].get('rpki_description', '')
                    if rpki_desc:
                        anomaly_name = f"RPKI: {rpki_desc.split('-')[0].strip()}"
                    else:
                        anomaly_name = f"RPKI {row['rpki_status']}"
                elif row['event_type'] == 'ml_anomaly':
                    # For ML, show which model detected it and severity
                    lstm_score = row['metadata'].get('lstm_score', 0)
                    iso_score = row['metadata'].get('iso_score', 0)
                    z_lstm = row['metadata'].get('z_lstm', 0)
                    z_iso = row['metadata'].get('z_iso', 0)
                    
                    # Determine which model had stronger signal
                    if abs(z_lstm) > abs(z_iso) * 2:
                        anomaly_name = f"LSTM Anomaly (z={z_lstm:.1f})"
                    elif abs(z_iso) > abs(z_lstm) * 2:
                        anomaly_name = f"Isolation Forest (score={iso_score:.2f})"
                    else:
                        anomaly_name = f"ML Ensemble (LSTM+IF)"
            
            anomalies.append({
                'id': row['id'],
                'timestamp': row['timestamp'].isoformat() if row['timestamp'] else None,
                'prefix': row['prefix'],
                'asn': row['origin_as'],
                'type': anomaly_name,  # Specific anomaly name
                'classification': row['classification'],  # Keep classification for grouping
                'severity': row['combined_severity'] or 'low',
                'score': float(row['combined_score']) if row['combined_score'] else 0.0,
                'rpkiStatus': row['rpki_status'],
                'eventType': row['event_type'],
                'rca': rca
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'anomalies': anomalies,
            'total': len(anomalies)
        })
    except Exception as e:
        logger.error(f"Error in dashboard/anomalies: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard/flaps', methods=['GET'])
def get_dashboard_flaps():
    """Get route flap data for dashboard widget"""
    try:
        time_range = request.args.get('time_range', '24h')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get flap rate over time
        cursor.execute("""
            SELECT window_start as time, 
                   AVG(flap_count) as avgFlaps
            FROM bgp_features_1min
            WHERE window_start > NOW() - INTERVAL %s
            GROUP BY window_start
            ORDER BY window_start ASC
            LIMIT 60
        """, (time_range,))
        
        time_series = [{'time': row['time'].isoformat(), 
                       'flaps': float(row['avgflaps']) if row['avgflaps'] else 0} 
                      for row in cursor.fetchall()]
        
        # Get top flapping prefixes
        cursor.execute("""
            SELECT prefix, 
                   SUM(flap_count) as total_flaps
            FROM bgp_features_1min
            WHERE window_start > NOW() - INTERVAL %s
                AND flap_count > 0
            GROUP BY prefix
            ORDER BY total_flaps DESC
            LIMIT 5
        """, (time_range,))
        
        flapping_peers = [{'prefix': row['prefix'], 
                          'flaps': int(row['total_flaps'] or 0)} 
                         for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'timeSeries': time_series,
            'flappingPeers': flapping_peers,
            'threshold': 100
        })
    except Exception as e:
        logger.error(f"Error in dashboard/flaps: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard/message-volume', methods=['GET'])
def get_dashboard_message_volume():
    """Get BGP message volume for dashboard widget"""
    try:
        time_range = request.args.get('time_range', '24h')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get message volume over time
        cursor.execute("""
            SELECT window_start as time, 
                   SUM(total_updates) as volume
            FROM bgp_features_1min
            WHERE window_start > NOW() - INTERVAL %s
            GROUP BY window_start
            ORDER BY window_start ASC
            LIMIT 60
        """, (time_range,))
        
        rows = cursor.fetchall()
        time_series = [{'time': row['time'].isoformat(), 
                       'volume': int(row['volume']) if row['volume'] else 0} 
                      for row in rows]
        
        avg_volume = sum(r['volume'] for r in time_series) / len(time_series) if time_series else 0
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'timeSeries': time_series,
            'averageVolume': int(avg_volume),
            'threshold': 100000
        })
    except Exception as e:
        logger.error(f"Error in dashboard/message-volume: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard/rpki-summary', methods=['GET'])
def get_dashboard_rpki_summary():
    """Get RPKI summary for dashboard widget"""
    try:
        time_range = request.args.get('time_range', '24h')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get RPKI status counts
        cursor.execute("""
            SELECT rpki_status, COUNT(*) as count
            FROM hybrid_anomaly_detections
            WHERE timestamp > NOW() - INTERVAL %s
                AND rpki_status IS NOT NULL
            GROUP BY rpki_status
        """, (time_range,))
        
        summary = {'valid': 0, 'invalid': 0, 'unknown': 0}
        for row in cursor.fetchall():
            status = (row['rpki_status'] or 'Unknown').lower()
            if 'valid' in status and 'invalid' not in status:
                summary['valid'] += row['count']
            elif 'invalid' in status:
                summary['invalid'] += row['count']
            else:
                summary['unknown'] += row['count']
        
        # Get top invalid prefixes (case-insensitive)
        cursor.execute("""
            SELECT prefix, origin_as, COUNT(*) as count
            FROM hybrid_anomaly_detections
            WHERE timestamp > NOW() - INTERVAL %s
                AND LOWER(rpki_status) LIKE '%%invalid%%'
            GROUP BY prefix, origin_as
            ORDER BY count DESC
            LIMIT 5
        """, (time_range,))
        
        invalid_prefixes = [{'prefix': row['prefix'], 
                            'asn': row['origin_as'], 
                            'count': row['count']} 
                           for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'summary': summary,
            'invalidPrefixes': invalid_prefixes
        })
    except Exception as e:
        logger.error(f"Error in dashboard/rpki-summary: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================
# Prefix Forensics Endpoints
# ============================================

@app.route('/api/prefixes', methods=['GET'])
def get_prefixes_list():
    """Get paginated prefix list for forensics page"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        time_range = request.args.get('time_range', '24h')
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get comprehensive prefix data by joining anomaly and features tables
        cursor.execute("""
            WITH prefix_anomalies AS (
                SELECT 
                    prefix,
                    COUNT(*) as anomaly_count,
                    MAX(combined_severity) as max_severity,
                    MAX(timestamp) as last_update,
                    MAX(origin_as) as asn,
                    MAX(rpki_status) as rpki_status,
                    ARRAY_AGG(DISTINCT classification) FILTER (WHERE classification IS NOT NULL) as anomaly_tags
                FROM hybrid_anomaly_detections
                WHERE timestamp > NOW() - INTERVAL %s
                GROUP BY prefix
            ),
            prefix_features AS (
                SELECT 
                    prefix::text,
                    SUM(flap_count) as flap_count,
                    SUM(announcements + withdrawals) as total_churn,
                    AVG(path_length) as avg_path_length
                FROM bgp_features_1min
                WHERE window_start > NOW() - INTERVAL %s
                GROUP BY prefix::text
            )
            SELECT 
                pa.prefix,
                pa.asn,
                pa.rpki_status as "rpkiStatus",
                COALESCE(ROUND(pf.avg_path_length), 0) as "pathLength",
                COALESCE(pf.flap_count, 0) as "flapCount",
                COALESCE(ROUND(pf.total_churn::numeric / EXTRACT(EPOCH FROM INTERVAL %s)::numeric * 3600, 2), 0) as "churnRate",
                pa.last_update as "lastUpdate",
                pa.anomaly_count as "anomalyCount",
                pa.max_severity as "severity",
                pa.anomaly_tags as "anomalyTags"
            FROM prefix_anomalies pa
            LEFT JOIN prefix_features pf ON pa.prefix = pf.prefix
            ORDER BY pa.anomaly_count DESC
            LIMIT %s OFFSET %s
        """, (time_range, time_range, time_range, limit, offset))
        
        prefixes = []
        for row in cursor.fetchall():
            prefix_data = dict(row)
            # Format timestamp
            if prefix_data.get('lastUpdate'):
                prefix_data['lastUpdate'] = prefix_data['lastUpdate'].isoformat()
            # Ensure anomalyTags is a list
            if not prefix_data.get('anomalyTags'):
                prefix_data['anomalyTags'] = []
            # Calculate activity level based on anomaly count
            anomaly_count = prefix_data.get('anomalyCount', 0)
            if anomaly_count > 100:
                prefix_data['activity'] = 'high'
            elif anomaly_count > 20:
                prefix_data['activity'] = 'medium'
            else:
                prefix_data['activity'] = 'low'
            
            prefixes.append(prefix_data)
        
        # Get total count
        cursor.execute("""
            SELECT COUNT(DISTINCT prefix) as total
            FROM hybrid_anomaly_detections
            WHERE timestamp > NOW() - INTERVAL %s
        """, (time_range,))
        
        total = cursor.fetchone()['total']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'prefixes': prefixes,
            'total': total,
            'page': page,
            'totalPages': (total + limit - 1) // limit
        })
    except Exception as e:
        logger.error(f"Error in prefixes: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/prefixes/<path:prefix>', methods=['GET'])
def get_prefix_details(prefix):
    """Get detailed information for a specific prefix"""
    try:
        time_range = request.args.get('time_range', '24h')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get prefix detections
        cursor.execute("""
            SELECT *
            FROM hybrid_anomaly_detections
            WHERE prefix = %s
                AND timestamp > NOW() - INTERVAL %s
            ORDER BY timestamp DESC
            LIMIT 100
        """, (prefix, time_range))
        
        detections = [dict(row) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'prefix': prefix,
            'detections': detections
        })
    except Exception as e:
        logger.error(f"Error in prefix details: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================
# Analytics Endpoints
# ============================================

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    """Get analytics data"""
    try:
        time_range = request.args.get('time_range', '24h')
        logger.info(f"Analytics requested with time_range: {time_range}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Anomaly trends over time
        cursor.execute("""
            SELECT DATE_TRUNC('hour', timestamp) as hour,
                   classification,
                   COUNT(*) as count
            FROM hybrid_anomaly_detections
            WHERE timestamp > NOW() - INTERVAL %s
                AND classification IS NOT NULL
            GROUP BY hour, classification
            ORDER BY hour ASC
        """, (time_range,))
        
        trends_rows = cursor.fetchall()
        logger.info(f"Anomaly trends query returned {len(trends_rows)} rows")
        
        trends_data = {}
        for row in trends_rows:
            hour_str = row['hour'].isoformat()
            if hour_str not in trends_data:
                trends_data[hour_str] = {'time': hour_str, 'count': 0}
            trends_data[hour_str][row['classification']] = row['count']
            trends_data[hour_str]['count'] += row['count']
        
        anomaly_trends = list(trends_data.values())
        
        # Prefix Behavior - scatter plot (announcements vs withdrawals per prefix)
        cursor.execute("""
            SELECT prefix,
                   SUM(announcements) as update_rate,
                   SUM(withdrawals) as withdrawal_rate
            FROM bgp_features_1min
            WHERE window_start > NOW() - INTERVAL %s
                AND prefix IS NOT NULL
            GROUP BY prefix
            HAVING SUM(announcements) > 0 OR SUM(withdrawals) > 0
            ORDER BY (SUM(announcements) + SUM(withdrawals)) DESC
            LIMIT 100
        """, (time_range,))
        
        prefix_behavior = [{'updateRate': row['update_rate'], 'withdrawalRate': row['withdrawal_rate']} 
                          for row in cursor.fetchall()]
        logger.info(f"Prefix behavior: {len(prefix_behavior)} prefixes")
        
        # Traffic Correlation (volume vs anomaly count)
        cursor.execute("""
            SELECT 
                DATE_TRUNC('hour', f.window_start) as time_bucket,
                SUM(f.total_updates) as traffic,
                COUNT(a.id) as anomaly_count
            FROM bgp_features_1min f
            LEFT JOIN hybrid_anomaly_detections a 
                ON DATE_TRUNC('hour', a.timestamp) = DATE_TRUNC('hour', f.window_start)
                AND a.timestamp > NOW() - INTERVAL %s
            WHERE f.window_start > NOW() - INTERVAL %s
            GROUP BY time_bucket
            HAVING SUM(f.total_updates) > 0
            ORDER BY time_bucket
            LIMIT 100
        """, (time_range, time_range))
        
        traffic_correlation = [{'traffic': int(row['traffic'] or 0), 'anomalyCount': int(row['anomaly_count'] or 0)} 
                              for row in cursor.fetchall()]
        logger.info(f"Traffic correlation: {len(traffic_correlation)} points")
        
        # RPKI Trends over time
        cursor.execute("""
            SELECT DATE_TRUNC('hour', timestamp) as time,
                   SUM(CASE WHEN LOWER(rpki_status) = 'valid' THEN 1 ELSE 0 END) as valid,
                   SUM(CASE WHEN LOWER(rpki_status) = 'invalid' THEN 1 ELSE 0 END) as invalid,
                   SUM(CASE WHEN LOWER(rpki_status) = 'unknown' OR rpki_status IS NULL THEN 1 ELSE 0 END) as unknown
            FROM hybrid_anomaly_detections
            WHERE timestamp > NOW() - INTERVAL %s
            GROUP BY time
            ORDER BY time ASC
        """, (time_range,))
        
        rpki_trends = [{'time': row['time'].isoformat(), 'valid': row['valid'], 
                       'invalid': row['invalid'], 'unknown': row['unknown']} 
                      for row in cursor.fetchall()]
        logger.info(f"RPKI trends: {len(rpki_trends)} points")
        
        # Top ASNs by anomaly count
        cursor.execute("""
            SELECT origin_as, COUNT(*) as count
            FROM hybrid_anomaly_detections
            WHERE timestamp > NOW() - INTERVAL %s
                AND origin_as IS NOT NULL
            GROUP BY origin_as
            ORDER BY count DESC
            LIMIT 10
        """, (time_range,))
        
        asn_rows = cursor.fetchall()
        logger.info(f"Top ASNs query returned {len(asn_rows)} rows")
        
        top_asns = [{'asn': row['origin_as'], 'count': row['count']} 
                   for row in asn_rows]
        
        # Summary stats with all fields
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN combined_severity = 'critical' THEN 1 ELSE 0 END) as critical,
                AVG(CASE WHEN combined_score IS NOT NULL THEN combined_score ELSE 0 END) as avg_score
            FROM hybrid_anomaly_detections
            WHERE timestamp > NOW() - INTERVAL %s
        """, (time_range,))
        
        stats_row = cursor.fetchone()
        
        # Calculate detection rate (anomalies per total updates)
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN SUM(total_updates) > 0 THEN 
                        (SELECT COUNT(*) FROM hybrid_anomaly_detections WHERE timestamp > NOW() - INTERVAL %s) * 100.0 / SUM(total_updates)
                    ELSE 0
                END as rate
            FROM bgp_features_1min
            WHERE window_start > NOW() - INTERVAL %s
        """, (time_range, time_range))
        
        rate_row = cursor.fetchone()
        detection_rate = round(rate_row['rate'] or 0.0, 2)
        
        logger.info(f"Stats: total={stats_row['total']}, critical={stats_row['critical']}, avg_score={stats_row['avg_score']}, rate={detection_rate}%")
        
        stats = {
            'totalAnomalies': stats_row['total'],
            'criticalCount': stats_row['critical'] if stats_row['critical'] else 0,
            'avgScore': round(float(stats_row['avg_score'] or 0.0), 2),
            'detectionRate': f"{detection_rate}%"
        }
        
        cursor.close()
        conn.close()
        
        result = {
            'anomalyTrends': anomaly_trends,
            'prefixBehavior': prefix_behavior,
            'trafficCorrelation': traffic_correlation,
            'rpkiTrends': rpki_trends,
            'stats': stats,
            'topAsns': top_asns
        }
        
        logger.info(f"Analytics response: {len(anomaly_trends)} trends, {len(prefix_behavior)} prefixes, {len(traffic_correlation)} traffic points, {len(rpki_trends)} RPKI points, {len(top_asns)} ASNs")
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in analytics: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/historical', methods=['GET'])
def get_historical():
    """Get historical playback data"""
    try:
        start = request.args.get('start')
        end = request.args.get('end')
        granularity = request.args.get('granularity', '5m')
        
        # Map granularity to PostgreSQL DATE_TRUNC unit (not interval)
        granularity_map = {
            '1m': 'minute',
            '5m': 'minute',  # Will aggregate 5 minutes manually
            '15m': 'minute',
            '30m': 'minute',
            '1h': 'hour',
            '6h': 'hour',
            '1d': 'day'
        }
        
        trunc_unit = granularity_map.get(granularity, 'minute')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get aggregated data over time with proper granularity
        cursor.execute("""
            SELECT 
                DATE_TRUNC(%s, window_start) as time,
                SUM(announcements) as announcements,
                SUM(withdrawals) as withdrawals,
                SUM(flap_count) as flaps,
                SUM(total_updates) as volume
            FROM bgp_features_1min
            WHERE window_start BETWEEN %s AND %s
            GROUP BY DATE_TRUNC(%s, window_start)
            ORDER BY time ASC
            LIMIT 2000
        """, (trunc_unit, start, end, trunc_unit))
        
        data = []
        for row in cursor.fetchall():
            data.append({
                'time': row['time'].isoformat(),
                'churn': int(row['announcements'] or 0) + int(row['withdrawals'] or 0),
                'flaps': int(row['flaps'] or 0),
                'volume': int(row['volume'] or 0),
                'announcements': int(row['announcements'] or 0),
                'withdrawals': int(row['withdrawals'] or 0)
            })
        
        # Get anomalies in time range with same granularity bucketing
        cursor.execute("""
            SELECT DATE_TRUNC(%s, timestamp) as time, COUNT(*) as count
            FROM hybrid_anomaly_detections
            WHERE timestamp BETWEEN %s AND %s
            GROUP BY DATE_TRUNC(%s, timestamp)
            ORDER BY time ASC
        """, (trunc_unit, start, end, trunc_unit))
        
        anomaly_map = {row['time'].isoformat(): row['count'] for row in cursor.fetchall()}
        
        # Add anomaly counts to data
        for item in data:
            item['anomalies'] = anomaly_map.get(item['time'], 0)
        
        cursor.close()
        conn.close()
        
        logger.info(f"Historical data: {len(data)} points returned for granularity={granularity}")
        
        return jsonify({
            'data': data,
            'timeRange': {'start': start, 'end': end}
        })
    except Exception as e:
        logger.error(f"Error in historical: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# ============================================
# WebSocket Events & Real-Time Monitoring
# ============================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")
    emit('connection_established', {'status': 'connected', 'timestamp': datetime.now(timezone.utc).isoformat()})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('subscribe')
def handle_subscribe(data):
    """Handle subscription to specific data feeds"""
    feed = data.get('feed', 'anomalies')
    logger.info(f"Client {request.sid} subscribed to: {feed}")
    emit('subscribed', {'feed': feed, 'status': 'active'})

# Background thread for monitoring database changes
def monitor_database_changes():
    """
    Monitor database for all dashboard data and broadcast via WebSocket.
    Polls database every 5 seconds and emits consolidated dashboard updates.
    """
    logger.info("Starting database monitoring thread for real-time updates")
    last_detection_id = 0
    
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get latest detection ID and new anomalies since last check
            cursor.execute("""
                SELECT id as detection_id, timestamp, prefix, event_type, 
                       classification, combined_severity as severity, combined_score, metadata
                FROM hybrid_anomaly_detections
                WHERE id > %s
                ORDER BY id ASC
                LIMIT 50
            """, (last_detection_id,))
            
            new_detections = cursor.fetchall()
            
            if new_detections:
                logger.info(f"Found {len(new_detections)} new anomalies")
                
                # Update last seen ID
                last_detection_id = max(d['detection_id'] for d in new_detections)
                
                # Broadcast each new anomaly
                for detection in new_detections:
                    # Extract anomaly name from metadata
                    anomaly_name = detection['event_type']  # Default to event type
                    metadata = detection.get('metadata', {})
                    
                    event_type_lower = detection['event_type'].lower() if detection['event_type'] else ''
                    
                    if event_type_lower == 'heuristic':
                        rules = metadata.get('triggered_rules', [])
                        if rules and len(rules) > 0:
                            anomaly_name = rules[0].get('rule_name', detection['event_type'])
                    elif event_type_lower == 'rpki':
                        anomaly_name = f"RPKI: {metadata.get('description', 'RPKI Invalid')}"
                    elif event_type_lower in ('ml', 'ml_anomaly'):
                        # Try both field name variations
                        z_lstm = float(metadata.get('z_lstm', metadata.get('z_score_lstm', 0)))
                        z_iso = float(metadata.get('z_iso', metadata.get('z_score_isolation_forest', 0)))
                        lstm_score = float(metadata.get('lstm_score', 0))
                        iso_score = float(metadata.get('iso_score', 0))
                        
                        # Determine which model had stronger signal
                        if abs(z_lstm) > abs(z_iso) * 2 and z_lstm != 0:
                            anomaly_name = f"LSTM Anomaly (z={z_lstm:.1f})"
                        elif abs(z_iso) > abs(z_lstm) * 2 and z_iso != 0:
                            anomaly_name = f"Isolation Forest (score={iso_score:.2f})"
                        else:
                            anomaly_name = "ML Ensemble (LSTM+IF)"
                    
                    anomaly_data = {
                        'id': detection['detection_id'],
                        'timestamp': detection['timestamp'].isoformat(),
                        'prefix': detection['prefix'],
                        'asn': detection.get('origin_as'),
                        'type': anomaly_name,
                        'eventType': detection['event_type'],
                        'classification': detection['classification'] or 'NORMAL',
                        'severity': detection['severity'],
                        'score': float(detection['combined_score'] or 0)
                    }
                    
                    # Broadcast to all connected clients
                    socketio.emit('new_anomaly', anomaly_data)
                
                # Also send summary update
                cursor.execute("""
                    SELECT COUNT(*) as total,
                           COUNT(*) FILTER (WHERE combined_severity = 'critical') as critical,
                           COUNT(*) FILTER (WHERE combined_severity = 'high') as high,
                           COUNT(*) FILTER (WHERE combined_severity = 'medium') as medium,
                           COUNT(*) FILTER (WHERE classification = 'HIJACK') as hijacks,
                           COUNT(*) FILTER (WHERE classification = 'LEAK') as leaks
                    FROM hybrid_anomaly_detections
                    WHERE timestamp > NOW() - INTERVAL '1 hour'
                """)
                
                stats = cursor.fetchone()
                socketio.emit('anomaly_stats', {
                    'total': stats['total'],
                    'critical': stats['critical'],
                    'high': stats['high'],
                    'medium': stats['medium'],
                    'hijacks': stats['hijacks'],
                    'leaks': stats['leaks'],
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            
            # Emit consolidated dashboard update every 5 seconds (always, not just on new anomalies)
            try:
                # Churn data
                cursor.execute("""
                    SELECT window_start as time, 
                           SUM(announcements) as announcements,
                           SUM(withdrawals) as withdrawals
                    FROM bgp_features_1min
                    WHERE window_start > NOW() - INTERVAL '1 hour'
                    GROUP BY window_start
                    ORDER BY window_start ASC
                    LIMIT 60
                """)
                churn_series = [{'time': row['time'].isoformat(), 
                               'announcements': int(row['announcements'] or 0), 
                               'withdrawals': int(row['withdrawals'] or 0)} 
                              for row in cursor.fetchall()]
                
                cursor.execute("""
                    SELECT prefix, SUM(announcements + withdrawals) as count
                    FROM bgp_features_1min
                    WHERE window_start > NOW() - INTERVAL '1 hour'
                    GROUP BY prefix
                    ORDER BY count DESC
                    LIMIT 10
                """)
                churn_top = [{'prefix': row['prefix'], 'count': int(row['count'])} 
                            for row in cursor.fetchall()]
                
                # Flaps data
                cursor.execute("""
                    SELECT window_start as time, SUM(flap_count) as flaps
                    FROM bgp_features_1min
                    WHERE window_start > NOW() - INTERVAL '1 hour'
                    GROUP BY window_start
                    ORDER BY window_start ASC
                    LIMIT 60
                """)
                flaps_series = [{'time': row['time'].isoformat(), 'flaps': int(row['flaps'] or 0)} 
                               for row in cursor.fetchall()]
                
                cursor.execute("""
                    SELECT prefix, SUM(flap_count) as flapCount
                    FROM bgp_features_1min
                    WHERE window_start > NOW() - INTERVAL '1 hour'
                    GROUP BY prefix
                    HAVING SUM(flap_count) > 10
                    ORDER BY flapCount DESC
                    LIMIT 10
                """)
                flaps_peers = [{'prefix': row['prefix'], 'flapCount': int(row['flapcount']), 
                               'rate': int(row['flapcount']), 'status': 'unstable' if row['flapcount'] > 50 else 'stable'} 
                              for row in cursor.fetchall()]
                
                # Volume data
                cursor.execute("""
                    SELECT window_start as time, SUM(total_updates) as volume
                    FROM bgp_features_1min
                    WHERE window_start > NOW() - INTERVAL '1 hour'
                    GROUP BY window_start
                    ORDER BY window_start ASC
                    LIMIT 60
                """)
                volume_series = [{'time': row['time'].isoformat(), 'volume': int(row['volume'] or 0)} 
                                for row in cursor.fetchall()]
                
                avg_volume = sum(v['volume'] for v in volume_series) / len(volume_series) if volume_series else 0
                
                # RPKI data
                cursor.execute("""
                    SELECT rpki_status, COUNT(*) as count
                    FROM hybrid_anomaly_detections
                    WHERE timestamp > NOW() - INTERVAL '1 hour'
                    GROUP BY rpki_status
                """)
                rpki_counts = {row['rpki_status']: row['count'] for row in cursor.fetchall()}
                
                cursor.execute("""
                    SELECT prefix, origin_as
                    FROM hybrid_anomaly_detections
                    WHERE timestamp > NOW() - INTERVAL '1 hour'
                      AND LOWER(rpki_status) = 'invalid'
                    ORDER BY timestamp DESC
                    LIMIT 5
                """)
                rpki_invalid = [{'prefix': row['prefix'], 'asn': row['origin_as']} 
                               for row in cursor.fetchall()]
                
                # Emit consolidated update
                socketio.emit('dashboard_update', {
                    'churn': {
                        'timeSeries': churn_series,
                        'topPrefixes': churn_top
                    },
                    'flaps': {
                        'timeSeries': flaps_series,
                        'peers': flaps_peers,
                        'threshold': 10,
                        'alerts': []
                    },
                    'volume': {
                        'timeSeries': volume_series,
                        'averageVolume': avg_volume
                    },
                    'rpki': {
                        'summary': {
                            'valid': rpki_counts.get('valid', 0),
                            'invalid': rpki_counts.get('invalid', 0),
                            'unknown': rpki_counts.get('unknown', 0)
                        },
                        'invalidPrefixes': rpki_invalid
                    },
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
                
            except Exception as dashboard_error:
                logger.error(f"Error generating dashboard update: {dashboard_error}")
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error in database monitoring: {e}")
        
        # Poll every 5 seconds
        time.sleep(5)

# Start monitoring thread
monitoring_thread = None

def start_monitoring():
    """Start the database monitoring thread"""
    global monitoring_thread
    if monitoring_thread is None:
        monitoring_thread = threading.Thread(target=monitor_database_changes, daemon=True)
        monitoring_thread.start()
        logger.info("Database monitoring thread started")

if __name__ == '__main__':
    logger.info("Starting React Dashboard API Server with WebSocket support")
    logger.info("API available at: http://localhost:5000")
    logger.info("WebSocket available at: ws://localhost:5000/socket.io/")
    
    # Start database monitoring
    start_monitoring()
    
    # Use socketio.run instead of app.run for WebSocket support
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)
