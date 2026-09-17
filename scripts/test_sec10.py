import requests
import json
import os

BASE_URL = "http://localhost:8001/api/v1"

def main():
    print("Testing SEC-10 Revocation Flow...")
    
    # 1. Login
    session = requests.Session()
    login_resp = session.post(f"{BASE_URL}/auth/login", json={"email": "admin@example.com", "password": "Admin@123"})
    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.text}")
        return
        
    print("Login OK")
    
    # 2. Check Protected API
    me_resp = session.get(f"{BASE_URL}/auth/me")
    if me_resp.status_code != 200:
        print(f"/auth/me failed: {me_resp.text}")
        return
        
    print("Protected API (/auth/me) OK")
    
    # Save the cookies manually before logout
    old_cookies = session.cookies.get_dict()
    
    # 3. Logout
    logout_resp = session.post(f"{BASE_URL}/auth/logout")
    if logout_resp.status_code != 200:
        print(f"Logout failed: {logout_resp.text}")
        return
        
    print("Logout OK")
    
    # 4. Reuse old access token
    test_session = requests.Session()
    requests.utils.add_dict_to_cookiejar(test_session.cookies, old_cookies)
    
    me_after_logout = test_session.get(f"{BASE_URL}/auth/me")
    print(f"Protected API (/auth/me) AFTER logout returned status: {me_after_logout.status_code}")
    if me_after_logout.status_code != 401:
        print(f"SEC-10 FAILED! Expected 401, got {me_after_logout.status_code}")
        return
        
    print("Protected API (/auth/me) REJECTED old token - SEC-10 FIXED")
    
    # 5. Refresh after logout
    refresh_after_logout = test_session.post(f"{BASE_URL}/auth/refresh")
    print(f"Refresh API AFTER logout returned status: {refresh_after_logout.status_code}")
    if refresh_after_logout.status_code != 401:
        print(f"SEC-10 FAILED! Expected 401 on refresh, got {refresh_after_logout.status_code}")
        return
        
    print("Refresh API REJECTED old refresh token - SEC-10 FIXED")
    
    print("All SEC-10 tests passed successfully!")

if __name__ == "__main__":
    main()
