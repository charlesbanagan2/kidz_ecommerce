"""
Kids & Baby E-commerce Platform - Application Launcher
Run this file to start the application
"""
from app import app, db, socketio

def initialize_database():
    """Initialize database and create default admin user if needed"""
    with app.app_context():
        # Create all database tables
        db.create_all()
        print("[OK] Database tables created/verified")
        
        # Check if admin user exists
        from app import User, Category, ThemeSetting
        admin = User.query.filter_by(email='admin@kidscommerce.com').first()
        
        if not admin:
            print("Creating default admin user...")
            admin = User(
                first_name='Admin',
                last_name='User',
                email='admin@kidscommerce.com',
                password='admin123',  # Change this in production!
                phone='1234567890',
                address='Admin Office',
                role='admin',
                status='active',
                email_verified=True
            )
            db.session.add(admin)
            db.session.commit()
            print("[OK] Default admin user created")
            print("  Email: admin@kidscommerce.com")
            print("  Password: admin123")
        
        # Create default categories if none exist
        if Category.query.count() == 0:
            print("Creating default categories...")
            categories = [
                Category(name='Baby Clothes & Accessories', status='active'),
                Category(name='Toys & Games', status='active'),
                Category(name='Strollers & Gear', status='active'),
                Category(name='Nursery Furniture', status='active'),
                Category(name='Safety and Health', status='active'),
                Category(name='Educational Materials', status='active'),
            ]
            for cat in categories:
                db.session.add(cat)
            db.session.commit()
            print("[OK] Default categories created")
        
        # Create theme settings if not exists
        if ThemeSetting.query.first() is None:
            print("Creating default theme settings...")
            theme = ThemeSetting(
                site_name='Kids & Baby Store',
                primary_color='#0066ff',
                secondary_color='#59b5fc',
                footer_color='#232323'
            )
            db.session.add(theme)
            db.session.commit()
            print("[OK] Default theme settings created")

if __name__ == '__main__':
    print("=" * 60)
    print("Kids & Baby E-commerce Platform")
    print("=" * 60)
    
    # Initialize database
    initialize_database()
    
    print("\nStarting application...")
    print("Access the application at: http://localhost:5000")
    print("Press CTRL+C to stop the server\n")
    print("=" * 60)
    
    # Run with SocketIO to enable real-time features
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
