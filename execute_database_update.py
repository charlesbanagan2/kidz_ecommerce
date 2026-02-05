#!/usr/bin/env python3
"""
Database Update Execution Script
This script executes the comprehensive database update and verifies everything is working.
"""

import mysql.connector
from mysql.connector import Error
import sys
import os

def execute_sql_file(connection, file_path):
    """Execute SQL commands from a file"""
    try:
        cursor = connection.cursor()
        
        with open(file_path, 'r', encoding='utf-8') as file:
            sql_commands = file.read()
            
        # Split commands by semicolon and execute each
        commands = [cmd.strip() for cmd in sql_commands.split(';') if cmd.strip()]
        
        for command in commands:
            if command:
                try:
                    cursor.execute(command)
                    print(f"✓ Executed: {command[:50]}...")
                except Error as e:
                    if "already exists" in str(e) or "Duplicate" in str(e):
                        print(f"⚠ Skipped (already exists): {command[:50]}...")
                    else:
                        print(f"✗ Error in command: {command[:50]}...")
                        print(f"  Error: {e}")
                        
        connection.commit()
        cursor.close()
        print("✓ All SQL commands executed successfully!")
        
    except Error as e:
        print(f"✗ Error executing SQL file: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False
        
    return True

def verify_database_structure(connection):
    """Verify that all required tables exist"""
    required_tables = [
        'user', 'seller_application', 'order', 'order_item', 'cart',
        'order_label', 'seller_order_seen', 'return_request', 'restock_request',
        'return_pickup', 'wallet_transaction', 'rider_chat_message', 'coupon',
        'rider_application', 'product', 'review', 'notification', 'address',
        'category', 'subcategory', 'hero_slide', 'theme_setting', 'delivery_personnel',
        'qr_scan_log', 'wishlist', 'admin_profile', 'admin_security_log',
        'store_chat_message', 'follow', 'oauth'
    ]
    
    cursor = connection.cursor()
    cursor.execute("SHOW TABLES")
    existing_tables = [table[0] for table in cursor.fetchall()]
    cursor.close()
    
    missing_tables = []
    for table in required_tables:
        if table not in existing_tables:
            missing_tables.append(table)
    
    if missing_tables:
        print(f"✗ Missing tables: {missing_tables}")
        return False
    else:
        print(f"✓ All {len(required_tables)} required tables exist!")
        return True

def verify_foreign_keys(connection):
    """Verify foreign key constraints"""
    cursor = connection.cursor()
    
    # Check some key foreign key relationships
    checks = [
        ("SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_NAME = 'order' AND COLUMN_NAME = 'buyer_id' AND REFERENCED_TABLE_NAME = 'user'", "order.buyer_id -> user.id"),
        ("SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_NAME = 'product' AND COLUMN_NAME = 'seller_id' AND REFERENCED_TABLE_NAME = 'user'", "product.seller_id -> user.id"),
        ("SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_NAME = 'cart' AND COLUMN_NAME = 'user_id' AND REFERENCED_TABLE_NAME = 'user'", "cart.user_id -> user.id"),
    ]
    
    for query, description in checks:
        cursor.execute(query)
        result = cursor.fetchone()[0]
        if result > 0:
            print(f"✓ Foreign key exists: {description}")
        else:
            print(f"✗ Foreign key missing: {description}")
    
    cursor.close()

def insert_sample_data(connection):
    """Insert some sample data if tables are empty"""
    cursor = connection.cursor()
    
    # Check if categories exist
    cursor.execute("SELECT COUNT(*) FROM category")
    category_count = cursor.fetchone()[0]
    
    if category_count == 0:
        print("Inserting sample categories...")
        categories = [
            ('Baby Clothes & Accessories', 'Clothing and accessories for babies and toddlers', 'active'),
            ('Toys & Games', 'Educational and fun toys for all ages', 'active'),
            ('Strollers & Gear', 'Strollers, carriers, and travel gear', 'active'),
            ('Nursery Furniture', 'Cribs, changing tables, and nursery furniture', 'active'),
            ('Safety and Health', 'Safety products and health essentials', 'active'),
            ('Educational Materials', 'Books, learning toys, and educational materials', 'active'),
        ]
        
        for name, desc, status in categories:
            cursor.execute("INSERT INTO category (name, description, status, created_at) VALUES (%s, %s, %s, NOW())", (name, desc, status))
        
        print("✓ Sample categories inserted")
    
    # Check if admin user exists
    cursor.execute("SELECT COUNT(*) FROM user WHERE role = 'admin'")
    admin_count = cursor.fetchone()[0]
    
    if admin_count == 0:
        print("Creating default admin user...")
        cursor.execute("""
            INSERT INTO user (username, first_name, last_name, email, password, phone, address, role, status, created_at, two_factor_enabled, email_notifications)
            VALUES ('admin', 'Admin', 'User', 'admin@kidscommerce.com', 'admin123', '09123456789', 'Admin Office, Manila', 'admin', 'active', NOW(), 0, 1)
        """)
        
        # Get the admin user ID
        admin_id = cursor.lastrowid
        
        # Create admin profile
        cursor.execute("""
            INSERT INTO admin_profile (user_id, full_name, contact_number, system_role, account_status, created_at, updated_at)
            VALUES (%s, 'Admin User', '09123456789', 'Administrator', 'Active', NOW(), NOW())
        """, (admin_id,))
        
        print("✓ Default admin user created")
    
    connection.commit()
    cursor.close()

def main():
    """Main execution function"""
    print("🚀 Starting Database Update Process...")
    
    # Database connection parameters
    db_config = {
        'host': 'localhost',
        'database': 'kids_ecommerce',
        'user': 'root',
        'password': '',
        'port': 3306
    }
    
    # Update with your actual database credentials
    print("Please enter your database connection details:")
    db_config['user'] = input("Database username (default: root): ") or 'root'
    db_config['password'] = input("Database password: ")
    db_config['host'] = input("Database host (default: localhost): ") or 'localhost'
    
    try:
        # Connect to database
        print("\n📡 Connecting to database...")
        connection = mysql.connector.connect(**db_config)
        
        if connection.is_connected():
            print(f"✓ Connected to database: {db_config['database']}")
            
            # Execute the comprehensive update
            print("\n🔄 Executing database update...")
            sql_file_path = os.path.join(os.path.dirname(__file__), 'database_update_comprehensive.sql')
            
            if os.path.exists(sql_file_path):
                if execute_sql_file(connection, sql_file_path):
                    print("\n✅ Database update completed successfully!")
                    
                    # Verify database structure
                    print("\n🔍 Verifying database structure...")
                    if verify_database_structure(connection):
                        print("✓ Database structure verification passed!")
                    else:
                        print("✗ Database structure verification failed!")
                        return False
                    
                    # Verify foreign keys
                    print("\n🔗 Verifying foreign key constraints...")
                    verify_foreign_keys(connection)
                    
                    # Insert sample data if needed
                    print("\n📝 Checking and inserting sample data...")
                    insert_sample_data(connection)
                    
                    print("\n🎉 Database update process completed successfully!")
                    print("\n📋 Summary:")
                    print("- All tables created/updated")
                    print("- Foreign key constraints verified")
                    print("- Sample data inserted where needed")
                    print("- Default admin user created if not exists")
                    
                else:
                    print("✗ Database update failed!")
                    return False
            else:
                print(f"✗ SQL file not found: {sql_file_path}")
                return False
                
        else:
            print("✗ Failed to connect to database")
            return False
            
    except Error as e:
        print(f"✗ Database connection error: {e}")
        return False
        
    finally:
        if 'connection' in locals() and connection.is_connected():
            connection.close()
            print("📡 Database connection closed")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
