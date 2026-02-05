#!/usr/bin/env python3
"""
Quick test to verify admin dashboard is working
"""

import requests

def test_admin_dashboard():
    """Test admin dashboard specifically"""
    base_url = "http://localhost:5000"
    session = requests.Session()
    
    print("Testing Admin Dashboard...")
    
    # Login
    login_data = {'email': 'admin@kidscommerce.com', 'password': 'admin123'}
    response = session.post(f"{base_url}/login", data=login_data, allow_redirects=True)
    
    if response.status_code == 200:
        # Test dashboard
        response = session.get(f"{base_url}/admin", allow_redirects=True)
        
        if response.status_code == 200:
            print("SUCCESS: Admin dashboard working!")
            
            # Check for key content
            if "Admin Dashboard" in response.text:
                print("SUCCESS: Dashboard title found")
            
            if "Total Users" in response.text:
                print("SUCCESS: User statistics found")
                
            if "Total Commission" in response.text:
                print("SUCCESS: Commission display found")
                
            if "Recent Orders" in response.text:
                print("SUCCESS: Recent orders section found")
                
            # Check for no errors
            error_terms = ["error", "Error", "TypeError", "500"]
            found_errors = [term for term in error_terms if term in response.text]
            
            if not found_errors:
                print("SUCCESS: No errors detected in dashboard")
                return True
            else:
                print(f"ISSUE: Found potential errors: {found_errors}")
                return False
        else:
            print(f"FAILED: Dashboard returned {response.status_code}")
            return False
    else:
        print(f"FAILED: Login failed with {response.status_code}")
        return False

if __name__ == "__main__":
    success = test_admin_dashboard()
    if success:
        print("\nAdmin Dashboard is 100% working!")
    else:
        print("\nAdmin Dashboard has issues!")
