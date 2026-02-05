#!/usr/bin/env python3
"""
Fix missing product_qr table using direct SQL
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
import pymysql

def create_table_direct_sql():
    """Create the missing product_qr table using direct SQL"""
    with app.app_context():
        try:
            print("Creating product_qr table using direct SQL...")
            
            # Get database connection details
            connection_string = app.config['SQLALCHEMY_DATABASE_URI']
            # Parse connection string: mysql+pymysql://root@127.0.0.1:3306/kids_ecommerce
            clean_uri = connection_string.replace('mysql+pymysql://', '').split('?')[0]  # Remove charset part
            parts = clean_uri.split('@')
            username = parts[0].split(':')[0] if ':' in parts[0] else parts[0]
            host_port_db = parts[1]
            host_port_parts = host_port_db.split('/')
            host_port = host_port_parts[0]
            database = host_port_parts[1]
            
            if ':' in host_port:
                host = host_port.split(':')[0]
                port = int(host_port.split(':')[1])
            else:
                host = host_port
                port = 3306
            
            print(f"Connecting to MySQL at {host}:{port}, database: {database}")
            
            # Direct connection
            conn = pymysql.connect(
                host=host,
                port=port,
                user=username,
                password='',  # No password based on connection string
                database=database,
                charset='utf8mb4'
            )
            
            cursor = conn.cursor()
            
            # SQL to create the table
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS `product_qr` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `product_id` int(11) NOT NULL,
              `qr_code` varchar(255) NOT NULL,
              `batch_number` varchar(50) DEFAULT NULL,
              `manufacturing_date` date DEFAULT NULL,
              `expiry_date` date DEFAULT NULL,
              `status` varchar(20) DEFAULT 'active',
              `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
              `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              PRIMARY KEY (`id`),
              UNIQUE KEY `qr_code` (`qr_code`),
              KEY `product_id` (`product_id`),
              CONSTRAINT `product_qr_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `product` (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
            """
            
            cursor.execute(create_table_sql)
            conn.commit()
            
            print("SUCCESS: product_qr table created!")
            
            # Verify the table exists
            cursor.execute("SHOW TABLES LIKE 'product_qr'")
            result = cursor.fetchone()
            
            if result:
                print("SUCCESS: Verification passed - table exists")
                cursor.execute("SELECT COUNT(*) FROM product_qr")
                count = cursor.fetchone()[0]
                print(f"Current records in product_qr: {count}")
                success = True
            else:
                print("ERROR: Verification failed - table not found")
                success = False
            
            cursor.close()
            conn.close()
            
            return success
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    success = create_table_direct_sql()
    if success:
        print("SUCCESS: Database fix completed!")
    else:
        print("FAILED: Database fix failed!")
    sys.exit(0 if success else 1)
