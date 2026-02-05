#!/usr/bin/env python3
"""
Quick script to fix stock for returned items
This will deduct 1 unit from product stock to match the return
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, Product

def fix_stock(product_id, deduction_amount=1):
    """Fix stock by deducting the specified amount"""
    with app.app_context():
        product = Product.query.get(product_id)
        if not product:
            print(f"Product {product_id} not found!")
            return False
        
        old_stock = product.stock
        product.stock -= deduction_amount
        
        # Ensure stock doesn't go below 0
        if product.stock < 0:
            product.stock = 0
        
        db.session.commit()
        
        print(f"Stock fixed for {product.name} (ID: {product_id})")
        print(f"Old stock: {old_stock} -> New stock: {product.stock}")
        print(f"Deducted: {deduction_amount} units")
        
        return True

if __name__ == "__main__":
    # Fix the product shown in the image (assuming it's product ID 1)
    # You can change the product_id as needed
    product_id = 1  # Change this to the actual product ID
    deduction = 1   # Deduct 1 unit for the returned item
    
    success = fix_stock(product_id, deduction)
    if success:
        print("✅ Stock correction completed successfully!")
    else:
        print("❌ Stock correction failed!")
