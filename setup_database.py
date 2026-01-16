#!/usr/bin/env python3
"""
BGP Monitoring System - Database Setup Script
This script initializes the PostgreSQL database with required tables and indexes.
"""

import os
import sys
import psycopg2
from psycopg2 import sql

def load_env():
    """Load environment variables from .env file if it exists."""
    env_file = '.env'
    if os.path.exists(env_file):
        print(f"Loading environment from {env_file}...")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

def get_db_config():
    """Get database configuration from environment or defaults."""
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'bgp_ensemble_db'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'your_password_here')
    }

def create_database(config):
    """Create the database if it doesn't exist."""
    print(f"\nChecking if database '{config['database']}' exists...")
    
    # Connect to default 'postgres' database to create our database
    temp_config = config.copy()
    temp_config['database'] = 'postgres'
    
    try:
        conn = psycopg2.connect(**temp_config)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (config['database'],)
        )
        exists = cursor.fetchone()
        
        if not exists:
            print(f"Creating database '{config['database']}'...")
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(config['database'])
                )
            )
            print(f" Database '{config['database']}' created successfully!")
        else:
            print(f" Database '{config['database']}' already exists.")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f" Error creating database: {e}")
        sys.exit(1)

def run_schema(config):
    """Execute the schema.sql file to create tables and indexes."""
    print(f"\nApplying database schema...")
    
    schema_file = 'schema.sql'
    if not os.path.exists(schema_file):
        print(f" Error: {schema_file} not found!")
        print("Please ensure schema.sql is in the same directory as this script.")
        sys.exit(1)
    
    try:
        # Read schema file
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        # Connect to database and execute schema
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        print("Creating tables and indexes...")
        cursor.execute(schema_sql)
        conn.commit()
        
        print(" Schema applied successfully!")
        
        # Verify tables were created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN (
                'ip_rib', 'l3vpn_rib', 'bgp_peers', 'bgp_features_1min',
                'rpki_validator', 'hybrid_anomaly_detections', 
                'correlated_detections', 'feature_aggregator_state',
                'ml_inference_state', 'heuristic_inference_state',
                'rpki_inference_state', 'correlation_engine_state'
            )
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        print(f"\n Successfully created {len(tables)} tables:")
        for table in tables:
            print(f"   - {table[0]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f" Error applying schema: {e}")
        sys.exit(1)

def verify_setup(config):
    """Verify the database setup is complete."""
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
    
    try:
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        # Check state tables have initial data
        state_tables = [
            'feature_aggregator_state',
            'ml_inference_state',
            'heuristic_inference_state',
            'rpki_inference_state',
            'correlation_engine_state'
        ]
        
        print("\nState tables initialized:")
        for table in state_tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            status = "" if count > 0 else ""
            print(f"   {status} {table}: {count} row(s)")
        
        cursor.close()
        conn.close()
        
        print("\n Database setup complete!")
        print("\nNext steps:")
        print("1. Start Routinator (RPKI validator)")
        print("2. Run: python main.py")
        print("3. Access dashboard at: http://localhost:5000")
        
    except Exception as e:
        print(f" Verification failed: {e}")
        sys.exit(1)

def main():
    """Main setup function."""
    print("="*60)
    print("BGP MONITORING SYSTEM - DATABASE SETUP")
    print("="*60)
    
    # Load environment variables
    load_env()
    
    # Get database configuration
    config = get_db_config()
    
    print(f"\nDatabase Configuration:")
    print(f"  Host: {config['host']}")
    print(f"  Port: {config['port']}")
    print(f"  Database: {config['database']}")
    print(f"  User: {config['user']}")
    
    # Confirm before proceeding
    response = input("\nProceed with database setup? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Setup cancelled.")
        sys.exit(0)
    
    # Create database
    create_database(config)
    
    # Run schema
    run_schema(config)
    
    # Verify setup
    verify_setup(config)

if __name__ == "__main__":
    main()
