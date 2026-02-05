#!/usr/bin/env python3
"""
Test admin restock requests with proper session handling
"""

import requests
import sys

def test_with_proper_session():
    """Test with proper session and cookie handling"""
    base_url = "http://localhost:5000"
    session = requests.Session()
    
    print("Testing with proper session handling...")
    print("=" * 50)
    
    # Step 1: Get login page to get CSRF token if needed
    print("1. Getting login page...")
    try:
        response = session.get(f"{base_url}/login")
        print(f"Login page status: {response.status_code}")
        if response.status_code != 200:
            print("Failed to get login page")
            return False
    except Exception as e:
        print(f"Error getting login page: {e}")
        return False
    
    # Step 2: Login with proper credentials
    print("2. Logging in...")
    try:
        login_data = {
            'email': 'admin@kidscommerce.com',
            'password': 'admin123'
        }
        response = session.post(f"{base_url}/login", data=login_data, allow_redirects=True)
        print(f"Login response status: {response.status_code}")
        
        # Check if login was successful by looking for admin content
        if response.status_code == 200:
            # Save cookies for debugging
            cookies = session.cookies.get_dict()
            print(f"Session cookies: {cookies}")
            
            if "admin" in response.text.lower() or "dashboard" in response.text.lower():
                print("Login appears successful")
            else:
                print("Login may have failed - no admin content found")
                print(f"Response preview: {response.text[:300]}...")
        else:
            print(f"Login failed with status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Error during login: {e}")
        return False
    
    # Step 3: Test admin dashboard first
    print("3. Testing admin dashboard...")
    try:
        response = session.get(f"{base_url}/admin", allow_redirects=True)
        print(f"Admin dashboard status: {response.status_code}")
        
        if response.status_code == 200:
            print("Admin dashboard accessible")
        else:
            print(f"Admin dashboard failed: {response.status_code}")
            if response.status_code == 302:
                print("Redirect detected - authentication issue")
            return False
            
    except Exception as e:
        print(f"Error accessing admin dashboard: {e}")
        return False
    
    # Step 4: Test restock requests page
    print("4. Testing restock requests page...")
    try:
        response = session.get(f"{base_url}/admin/restock-requests", allow_redirects=True)
        print(f"Restock requests status: {response.status_code}")
        
        if response.status_code == 200:
            print("SUCCESS - Restock requests page loaded!")
            
            # Check for expected content
            if "Restock Requests" in response.text:
                print("Page contains expected title")
            else:
                print("WARNING - Missing expected title")
                
            if "TypeError" not in response.text:
                print("No TypeError detected")
            else:
                print("ERROR - TypeError found in page")
                return False
                
            return True
            
        elif response.status_code == 500:
            print("ERROR - 500 Internal Server Error")
            print("Error response:")
            print(response.text[:1000])
            return False
            
        elif response.status_code == 302:
            print("ERROR - Redirect detected (authentication issue)")
            print("Redirect location:", response.headers.get('Location', 'Unknown'))
            return False
            
        else:
            print(f"ERROR - Unexpected status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Error accessing restock requests: {e}")
        return False

if __name__ == "__main__":
    success = test_with_proper_session()
    if success:
        print("=" * 50)
        print("SUCCESS - All tests passed!")
        print("The admin restock requests page is working correctly!")
    else:
        print("=" * 50)
        print("FAILED - Tests failed")
    
    sys.exit(0 if success else 1)
