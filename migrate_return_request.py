#!/usr/bin/env python3
"""
Database migration script to add missing columns to ReturnRequest table
Run this script once to update the database schema
"""

import sqlite3
import os
from datetime import datetime

def migrate_database():
    # Path to your database
    db_path = 'instance/kids_ecommerce.db'
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(return_request)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add missing columns if they don't exist
        migrations = [
            ("reason_other", "TEXT"),
            ("description", "TEXT"),
            ("quantity", "INTEGER DEFAULT 1"),
            ("images", "JSON"),  # SQLite doesn't have JSON type, will store as TEXT
            ("video_filename", "VARCHAR(255)"),
            ("seller_response_reason", "TEXT")
        ]
        
        for column_name, column_type in migrations:
            if column_name not in columns:
                print(f"Adding column: {column_name}")
                cursor.execute(f"ALTER TABLE return_request ADD COLUMN {column_name} {column_type}")
            else:
                print(f"Column {column_name} already exists")
        
        conn.commit()
        print("Database migration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
