"""
Update existing reviews to mark them as verified purchases
Run this once to update all existing reviews in the database
"""
from app import app, db, Review, Order, OrderItem
from datetime import datetime

with app.app_context():
    # Get all existing reviews
    reviews = Review.query.all()
    updated_count = 0
    
    for review in reviews:
        # Check if the reviewer purchased this product
        completed_orders = Order.query.filter(
            Order.buyer_id == review.user_id,
            Order.status.in_(['completed', 'delivered'])
        ).all()
        
        for order in completed_orders:
            for item in order.items:
                if item.product_id == review.product_id:
                    # Mark as verified purchase
                    review.verified_purchase = True
                    review.order_id = order.id
                    updated_count += 1
                    print(f"✓ Review #{review.id} marked as verified purchase (Order #{order.id})")
                    break
            if review.verified_purchase:
                break
        
        if not review.verified_purchase:
            print(f"✗ Review #{review.id} not a verified purchase")
    
    db.session.commit()
    print(f"\nUpdated {updated_count} out of {len(reviews)} reviews as verified purchases.")
