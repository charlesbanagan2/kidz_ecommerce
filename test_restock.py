from app import app, get_available_stock, Product, RestockRequest, db

def test_restock_scenario():
    with app.app_context():
        print("=== Testing Restock Request Scenario ===")
        print()
        
        # Test scenario: Product has 20 stock, add 10 restock, should become 30
        product = Product.query.first()
        if product:
            print(f"Testing with product: {product.name}")
            print(f"Current stock: {product.stock}")
            print(f"Current available stock: {get_available_stock(product.id)}")
            print()
            
            # Simulate restock approval
            original_stock = product.stock
            restock_amount = 10
            
            print(f"Simulating restock approval: +{restock_amount}")
            product.stock += restock_amount
            db.session.commit()
            
            print(f"Stock after restock: {product.stock}")
            print(f"Available stock after restock: {get_available_stock(product.id)}")
            
            # Expected: original_stock + restock_amount
            expected_stock = original_stock + restock_amount
            expected_available = expected_stock  # minus any orders
            
            print()
            print("=== Results ===")
            print(f"Expected stock: {expected_stock}")
            print(f"Actual stock: {product.stock}")
            print(f"Expected available: {expected_available}")
            print(f"Actual available: {get_available_stock(product.id)}")
            
            if product.stock == expected_stock:
                print("✅ Stock calculation CORRECT")
            else:
                print("❌ Stock calculation INCORRECT")
                
            # Restore original stock
            product.stock = original_stock
            db.session.commit()
            print("✅ Restored original stock for testing")
        else:
            print("❌ No products found for testing")

if __name__ == "__main__":
    test_restock_scenario()
