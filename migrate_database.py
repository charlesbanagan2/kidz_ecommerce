#!/usr/bin/env python3
"""
Database migration script to add missing columns to return_request table
"""

import pymysql
from pymysql.cursors import DictCursor
import sys

def get_db_connection():
    """Get database connection from .env file"""
    try:
        with open('.env', 'r') as f:
            env_content = f.read()
        
        # Parse .env file
        env_vars = {}
        for line in env_content.strip().split('\n'):
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
        
        # Connect to database
        connection = pymysql.connect(
            host=env_vars.get('DB_HOST', 'localhost'),
            user=env_vars.get('DB_USER', 'root'),
            password=env_vars.get('DB_PASSWORD', ''),
            database=env_vars.get('DB_NAME', 'kids_ecommerce'),
            cursorclass=DictCursor
        )
        
        return connection
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def check_and_add_columns():
    """Check and add missing columns to return_request table"""
    connection = get_db_connection()
    
    try:
        with connection.cursor() as cursor:
            # Get existing columns in return_request table
            cursor.execute("DESCRIBE return_request")
            existing_columns = [row['Field'] for row in cursor.fetchall()]
            
            print("Existing columns:", existing_columns)
            
            # Columns to add (from the ReturnRequest model)
            columns_to_add = [
                ('processed_at', 'DATETIME'),
                ('processed_by', 'INT'),
                ('refund_amount', 'FLOAT'),
                ('admin_notes', 'TEXT'),
                ('updated_at', 'DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')
            ]
            
            for column_name, column_type in columns_to_add:
                if column_name not in existing_columns:
                    print(f"Adding column: {column_name}")
                    try:
                        if column_name == 'updated_at':
                            # Special handling for updated_at with ON UPDATE CURRENT_TIMESTAMP
                            sql = f"""
                            ALTER TABLE return_request 
                            ADD COLUMN {column_name} {column_type}
                            """
                        else:
                            sql = f"""
                            ALTER TABLE return_request 
                            ADD COLUMN {column_name} {column_type}
                            """
                        
                        cursor.execute(sql)
                        print(f"Added column: {column_name}")
                    except Exception as e:
                        print(f"Error adding column {column_name}: {e}")
                else:
                    print(f"Column {column_name} already exists")
            
            # Add foreign key constraints if they don't exist
            try:
                # Check if foreign key for processed_by exists
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM information_schema.KEY_COLUMN_USAGE 
                    WHERE TABLE_NAME = 'return_request' 
                    AND COLUMN_NAME = 'processed_by' 
                    AND REFERENCED_TABLE_NAME = 'user'
                """)
                
                if cursor.fetchone()['count'] == 0:
                    print("Adding foreign key constraint for processed_by")
                    cursor.execute("""
                        ALTER TABLE return_request 
                        ADD CONSTRAINT fk_return_request_processed_by 
                        FOREIGN KEY (processed_by) REFERENCES user(id)
                    """)
                    print("Added foreign key constraint for processed_by")
                else:
                    print("Foreign key constraint for processed_by already exists")
                    
            except Exception as e:
                print(f"Warning: Could not add foreign key constraint: {e}")
            
            connection.commit()
            print("\nDatabase migration completed successfully!")
            
    except Exception as e:
        print(f"Migration failed: {e}")
        connection.rollback()
        sys.exit(1)
    finally:
        connection.close()

def create_restock_request_table():
    """Create restock_request table if it doesn't exist"""
    connection = get_db_connection()
    
    try:
        with connection.cursor() as cursor:
            # Check if table exists
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM information_schema.tables 
                WHERE table_schema = DATABASE() 
                AND table_name = 'restock_request'
            """)
            
            if cursor.fetchone()['count'] == 0:
                print("Creating restock_request table...")
                
                cursor.execute("""
                    CREATE TABLE restock_request (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        product_id INT NOT NULL,
                        seller_id INT NOT NULL,
                        requested_quantity INT NOT NULL,
                        status VARCHAR(20) DEFAULT 'pending',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        processed_at DATETIME NULL,
                        processed_by INT NULL,
                        admin_notes TEXT NULL,
                        approved_quantity INT NULL,
                        FOREIGN KEY (product_id) REFERENCES product(id),
                        FOREIGN KEY (seller_id) REFERENCES user(id),
                        FOREIGN KEY (processed_by) REFERENCES user(id)
                    )
                """)
                
                print("Created restock_request table")
            else:
                print("restock_request table already exists")
            
            connection.commit()
            
    except Exception as e:
        print(f"Error creating restock_request table: {e}")
        connection.rollback()
        sys.exit(1)
    finally:
        connection.close()

if __name__ == "__main__":
    print("Starting database migration...")
    
    print("\n=== Migrating return_request table ===")
    check_and_add_columns()
    
    print("\n=== Creating restock_request table ===")
    create_restock_request_table()
    
    print("\nAll migrations completed successfully!")
    print("You can now restart your Flask application.")
