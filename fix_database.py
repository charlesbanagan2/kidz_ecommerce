#!/usr/bin/env python3
"""
Fix missing product_qr table
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, ProductQR

def create_missing_table():
    """Create the missing product_qr table"""
    with app.app_context():
        try:
            print("Creating missing product_qr table...")
            
            # Create just the ProductQR table
            ProductQR.__table__.create(db.engine, checkfirst=True)
            print("✅ product_qr table created successfully!")
            
            # Verify the table exists
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'product_qr' in tables:
                print("✅ Verification: product_qr table exists in database")
                print(f"Total tables in database: {len(tables)}")
                return True
            else:
                print("❌ Verification failed: table still doesn't exist")
                return False
                
        except Exception as e:
            print(f"❌ Error creating table: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    success = create_missing_table()
    sys.exit(0 if success else 1)
