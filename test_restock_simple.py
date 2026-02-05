#!/usr/bin/env python3
"""
Simple test to check RestockRequest model and admin route
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, RestockRequest, User, Product

def test_restock_model():
    """Test RestockRequest model directly"""
    with app.app_context():
        try:
            print("Testing RestockRequest model...")
            
            # Test query
            restock_requests = RestockRequest.query.all()
            print(f"Found {len(restock_requests)} restock requests")
            
            # Test building requests_data like in the route
            requests_data = []
            for req in restock_requests:
                try:
                    data = {
                        'id': req.id,
                        'product': req.product,
                        'seller': req.seller,
                        'requested_quantity': req.requested_quantity,
                        'approved_quantity': req.approved_quantity,
                        'status': req.status,
                        'created_at': req.created_at,
                        'processed_at': req.processed_at,
                        'admin_notes': req.admin_notes
                    }
                    requests_data.append(data)
                    print(f"Successfully processed request {req.id}")
                except Exception as e:
                    print(f"Error processing request {req.id}: {e}")
                    return False
            
            print(f"Successfully built requests_data with {len(requests_data)} items")
            return True
            
        except Exception as e:
            print(f"Error testing RestockRequest model: {e}")
            import traceback
            traceback.print_exc()
            return False

def test_admin_route_directly():
    """Test the admin route directly"""
    with app.test_client() as client:
        try:
            print("Testing admin route directly...")
            
            # Simulate admin login
            with client.session_transaction() as sess:
                sess['user_id'] = 1
                sess['role'] = 'admin'
            
            response = client.get('/admin/restock-requests')
            print(f"Route response status: {response.status_code}")
            
            if response.status_code == 500:
                print("500 Error detected")
                print("Response content:")
                print(response.get_data(as_text=True)[:1000])
                return False
            elif response.status_code == 200:
                print("Route successful")
                return True
            else:
                print(f"Unexpected status: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"Error testing admin route: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    print("Testing RestockRequest functionality...")
    print("=" * 50)
    
    # Test 1: Model directly
    if not test_restock_model():
        print("Model test failed")
        sys.exit(1)
    
    print()
    
    # Test 2: Admin route
    if not test_admin_route_directly():
        print("Route test failed")
        sys.exit(1)
    
    print("=" * 50)
    print("All tests passed!")
