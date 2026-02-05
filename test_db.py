from app import app, db
from sqlalchemy import text
with app.app_context():
    try:
        result = db.session.execute(text('SELECT 1')).scalar()
        print(f'Database connection: {result}')
        
        # Get table names
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        print(f'Tables: {tables[:10]}...')  # Show first 10 tables
        
        # Test a simple query
        from app import Category, Product, HeroSlide, SellerApplication
        
        print(f'Categories count: {Category.query.count()}')
        print(f'Products count: {Product.query.count()}')
        print(f'Hero slides count: {HeroSlide.query.count()}')
        print(f'Seller applications count: {SellerApplication.query.count()}')
        
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
       