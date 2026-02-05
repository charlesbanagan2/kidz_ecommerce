#!/usr/bin/env python3
"""
Database initialization script to update schema
Run this script to recreate the database with the updated schema
"""

from app import app, db, Category, User

def init_database():
    with app.app_context():
        print("Dropping existing tables...")
        db.drop_all()
        
        print("Creating new tables with updated schema...")
        db.create_all()
        
        # Create default categories
        categories = [
            'Baby Clothes & Accessories',
            'Toys & Games',
            'Strollers & Gear',
            'Nursery Furniture',
            'Safety and Health',
            'Educational Materials'
        ]
        
        print("Creating default categories...")
        for cat_name in categories:
            category = Category(name=cat_name)
            db.session.add(category)
        
        # Create admin user
        print("Creating admin user...")
        admin = User(
            username='admin',
            first_name='Admin',
            last_name='User',
            email='admin@kidscommerce.com',
            password='Admin123!',  # Professional password
            phone='09123456789',
            address='Admin Office, Manila',
            role='admin'
        )
        db.session.add(admin)
        
        # Create a sample buyer user for testing
        print("Creating sample buyer user...")
        buyer = User(
            username='buyer_test',
            first_name='John',
            last_name='Doe',
            email='buyer@test.com',
            password='Buyer123!',  # Professional password
            phone='09123456780',
            address='123 Test Street, Manila',
            role='buyer'
        )
        db.session.add(buyer)
        
        db.session.commit()
        print("SUCCESS: Database initialized successfully with updated schema!")
        print("Admin login: admin@kidscommerce.com (or 'admin') / Admin123!")
        print("Buyer login: buyer@test.com (or 'buyer_test') / Buyer123!")

if __name__ == '__main__':
    init_database()
