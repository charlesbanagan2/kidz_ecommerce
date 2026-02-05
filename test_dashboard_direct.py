#!/usr/bin/env python3
"""
Test admin dashboard route directly to find the exact error
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def test_admin_dashboard_directly():
    """Test the admin dashboard route directly"""
    with app.test_client() as client:
        try:
            print("Testing admin dashboard route directly...")
            
            # Simulate admin login
            with client.session_transaction() as sess:
                sess['user_id'] = 1
                sess['role'] = 'admin'
            
            response = client.get('/admin')
            print(f"Route response status: {response.status_code}")
            
            if response.status_code == 500:
                print("500 Error detected - analyzing...")
                print("Response content:")
                print(response.get_data(as_text=True))
                return False
            elif response.status_code == 200:
                print("Route successful!")
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
    success = test_admin_dashboard_directly()
    if success:
        print("Admin dashboard is working!")
    else:
        print("Admin dashboard has issues!")
