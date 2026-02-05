"""
Script to update categories to only show the 6 specified ones:
- Baby Clothes & Accessories
- Toys & Games
- Educational Materials
- Strollers & Gear
- Nursery Furniture
- Safety and Health

Run this script once to clean up old categories.
"""
from app import app, db, Category

# Categories to keep
VALID_CATEGORIES = [
    'Baby Clothes & Accessories',
    'Toys & Games',
    'Educational Materials',
    'Strollers & Gear',
    'Nursery Furniture',
    'Safety and Health'
]

with app.app_context():
    print("Updating categories...")
    
    # Get all existing categories
    all_categories = Category.query.all()
    
    # Mark old categories as inactive instead of deleting
    # (to preserve product relationships)
    for category in all_categories:
        if category.name not in VALID_CATEGORIES:
            category.status = 'inactive'
            print(f"✗ Marked '{category.name}' as inactive")
        else:
            category.status = 'active'
            print(f"✓ Kept '{category.name}' as active")
    
    # Create any missing categories
    existing_names = [cat.name for cat in all_categories]
    for cat_name in VALID_CATEGORIES:
        if cat_name not in existing_names:
            new_category = Category(name=cat_name, status='active')
            db.session.add(new_category)
            print(f"+ Created new category: '{cat_name}'")
    
    db.session.commit()
    
    # Show final active categories
    print("\n=== Active Categories ===")
    active_categories = Category.query.filter_by(status='active').order_by(Category.id).all()
    for cat in active_categories:
        product_count = len([p for p in cat.products if p.status == 'active'])
        print(f"{cat.id}. {cat.name} ({product_count} active products)")
    
    print("\nCategories updated successfully!")
    print("Note: Old categories are marked as 'inactive' to preserve product relationships.")
    print("Products in inactive categories won't show in navigation but remain in database.")
