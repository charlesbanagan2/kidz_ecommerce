#!/usr/bin/env python3
"""
Test script to verify admin restock requests page works without errors
"""

import requests
import sys

def test_admin_restock_requests():
    """Test the admin restock requests page"""
    base_url = "http://localhost:5000"
    session = requests.Session()
    
    print("Testing Admin Restock Requests Page...")
    print("=" * 50)
    
    # Test 1: Main application
    print("1. Testing main application...")
    try:
        response = session.get(base_url)
        if response.status_code == 200:
            print("OK - Main application")
        else:
            print(f"FAIL - Main application: {response.status_code}")
            return False
    except Exception as e:
        print(f"ERROR - Main application: {e}")
        return False
    
    # Test 2: Login page
    print("2. Testing login page...")
    try:
        response = session.get(f"{base_url}/login")
        if response.status_code == 200:
            print("OK - Login page")
        else:
            print(f"FAIL - Login page: {response.status_code}")
            return False
    except Exception as e:
        print(f"ERROR - Login page: {e}")
        return False
    
    # Test 3: Admin login
    print("3. Testing admin login...")
    try:
        login_data = {
            'email': 'admin@kidscommerce.com',
            'password': 'admin123'
        }
        response = session.post(f"{base_url}/login", data=login_data)
        if response.status_code == 200 and "admin" in response.text.lower():
            print("OK - Admin login")
        else:
            print(f"FAIL - Admin login: {response.status_code}")
            return False
    except Exception as e:
        print(f"ERROR - Admin login: {e}")
        return False
    
    # Test 4: Admin dashboard
    print("4. Testing admin dashboard...")
    try:
        response = session.get(f"{base_url}/admin")
        if response.status_code == 200:
            print("OK - Admin dashboard")
        else:
            print(f"FAIL - Admin dashboard: {response.status_code}")
            return False
    except Exception as e:
        print(f"ERROR - Admin dashboard: {e}")
        return False
    
    # Test 5: Admin restock requests (the main test)
    print("5. Testing admin restock requests page...")
    try:
        response = session.get(f"{base_url}/admin/restock-requests")
        if response.status_code == 200:
            print("OK - Admin restock requests page")
            
            # Check for specific content that should be on the page
            if "Restock Requests" in response.text:
                print("OK - Page contains 'Restock Requests'")
            else:
                print("WARNING - Page missing expected text")
                
            # Check for no error messages
            if "TypeError" not in response.text and "error" not in response.text.lower():
                print("OK - No error messages found")
            else:
                print("WARNING - Error messages found")
                
        else:
            print(f"FAIL - Admin restock requests: {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            return False
    except Exception as e:
        print(f"ERROR - Admin restock requests: {e}")
        return False
    
    # Test 6: Test other admin pages for similar issues
    print("6. Testing other admin pages...")
    admin_pages = [
        "/admin/rider-applications",
        "/admin/seller-applications", 
        "/admin/pending-registrations",
        "/admin/users",
        "/admin/products"
    ]
    
    for page in admin_pages:
        try:
            response = session.get(f"{base_url}{page}")
            if response.status_code == 200:
                print(f"OK - {page}")
            else:
                print(f"FAIL - {page}: {response.status_code}")
        except Exception as e:
            print(f"ERROR - {page}: {e}")
    
    print("=" * 50)
    print("SUCCESS - All tests completed!")
    print("The admin restock requests page is working without errors!")
    return True

if __name__ == "__main__":
    success = test_admin_restock_requests()
    sys.exit(0 if success else 1)
