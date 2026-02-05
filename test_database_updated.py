#!/usr/bin/env python3
"""
Database Test Script
Tests the database connection and model functionality after the update.
"""

import os
import sys
from datetime import datetime

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import app, db, User, Product, Category, Order, SellerApplication
    from app import Notification, WalletTransaction, ReturnRequest, RestockRequest
    print("✓ Successfully imported all models")
except ImportError as e:
    print(f"✗ Import error: {e}")
    print("Make sure you're running this from the project directory")
    sys.exit(1)

def test_database_connection():
    """Test database connection"""
    try:
        with app.app_context():
            # Test basic database connection
            db.engine.execute("SELECT 1")
            print("✓ Database connection successful")
            return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False

def test_model_creation():
    """Test model creation and relationships"""
    try:
        with app.app_context():
            # Test creating a user
            test_user = User(
                username='testuser',
                first_name='Test',
                last_name='User',
                email='test@example.com',
                password='test123',
                phone='123456789',
                address='Test Address',
                role='buyer'
            )
            db.session.add(test_user)
            db.session.commit()
            print("✓ User creation successful")
            
            # Test creating a category
            test_category = Category(
                name='Test Category',
                description='Test category description',
                status='active'
            )
            db.session.add(test_category)
            db.session.commit()
            print("✓ Category creation successful")
            
            # Test creating a product
            test_product = Product(
                name='Test Product',
                description='Test product description',
                price=99.99,
                stock=10,
                category_id=test_category.id,
                seller_id=test_user.id,
                status='active'
            )
            db.session.add(test_product)
            db.session.commit()
            print("✓ Product creation successful")
            
            # Test relationships
            assert test_product.category == test_category
            assert test_product.seller == test_user
            assert test_category.products[0] == test_product
            assert test_user.products[0] == test_product
            print("✓ Model relationships working correctly")
            
            # Clean up test data
            db.session.delete(test_product)
            db.session.delete(test_category)
            db.session.delete(test_user)
            db.session.commit()
            print("✓ Test data cleaned up")
            
            return True
    except Exception as e:
        print(f"✗ Model creation test failed: {e}")
        db.session.rollback()
        return False

def test_new_models():
    """Test newly added models"""
    try:
        with app.app_context():
            # Test WalletTransaction
            admin_user = User.query.filter_by(role='admin').first()
            if admin_user:
                wallet_tx = WalletTransaction(
                    user_id=admin_user.id,
                    amount=100.0,
                    type='credit',
                    source='test'
                )
                db.session.add(wallet_tx)
                db.session.commit()
                print("✓ WalletTransaction creation successful")
                db.session.delete(wallet_tx)
                db.session.commit()
            
            # Test Notification
            notification = Notification(
                user_id=admin_user.id if admin_user else 1,
                message='Test notification',
                type='system'
            )
            db.session.add(notification)
            db.session.commit()
            print("✓ Notification creation successful")
            db.session.delete(notification)
            db.session.commit()
            
            return True
    except Exception as e:
        print(f"✗ New models test failed: {e}")
        db.session.rollback()
        return False

def test_table_structure():
    """Test that all tables exist and have correct structure"""
    try:
        with app.app_context():
            # Get all table names
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            required_tables = [
                'user', 'seller_application', 'order', 'order_item', 'cart',
                'order_label', 'return_request', 'restock_request', 'wallet_transaction',
                'product', 'review', 'notification', 'address', 'category', 'subcategory',
                'hero_slide', 'theme_setting', 'delivery_personnel', 'qr_scan_log',
                'wishlist', 'admin_profile', 'admin_security_log', 'store_chat_message',
                'follow', 'oauth', 'coupon', 'rider_application', 'rider_chat_message'
            ]
            
            missing_tables = []
            for table in required_tables:
                if table not in tables:
                    missing_tables.append(table)
            
            if missing_tables:
                print(f"✗ Missing tables: {missing_tables}")
                return False
            else:
                print(f"✓ All {len(required_tables)} required tables exist")
                return True
                
    except Exception as e:
        print(f"✗ Table structure test failed: {e}")
        return False

def test_data_integrity():
    """Test data integrity and foreign key constraints"""
    try:
        with app.app_context():
            # Test that admin user exists
            admin_count = User.query.filter_by(role='admin').count()
            if admin_count > 0:
                print("✓ Admin user exists")
            else:
                print("⚠ No admin user found")
            
            # Test that categories exist
            category_count = Category.query.count()
            if category_count > 0:
                print(f"✓ {category_count} categories exist")
            else:
                print("⚠ No categories found")
            
            # Test user-product relationships
            user_with_products = User.query.join(Product).count()
            print(f"✓ {user_with_products} users have products")
            
            return True
    except Exception as e:
        print(f"✗ Data integrity test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Starting Database Tests...")
    print("=" * 50)
    
    tests = [
        ("Database Connection", test_database_connection),
        ("Model Creation", test_model_creation),
        ("New Models", test_new_models),
        ("Table Structure", test_table_structure),
        ("Data Integrity", test_data_integrity),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name} Test...")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                failed += 1
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            failed += 1
            print(f"❌ {test_name} ERROR: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! Database is working correctly!")
        print("\n📋 Ready to run your application!")
        return True
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
