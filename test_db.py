# test_db.py
from database import db
import json

def test_database():
    print("=" * 60)
    print("Testing Database Connection...")
    print("=" * 60)
    
    # Test getting data
    data = db.get_data()
    print(f"\nData structure keys: {list(data.keys())}")
    print(f"Users count: {len(data.get('users', []))}")
    print(f"Buildings count: {len(data.get('buildings', []))}")
    
    # Print users if any
    users = data.get("users", [])
    if users:
        print(f"\n✅ Users found in database: {len(users)}")
        print(f"User data: {json.dumps(users[0], indent=2)}")
    else:
        print("\nNo users found. Creating Super Admin...")
        db.init_super_admin()
        
        # Check again
        data = db.get_data()
        users = data.get("users", [])
        if users:
            print(f"✅ Super Admin created successfully!")
            print(f"User data: {json.dumps(users[0], indent=2)}")
        else:
            print("❌ Failed to create Super Admin")
    
    # Test adding a test user
    test_user = {
        "user_id": "testuser",
        "email": "test@example.com",
        "username": "Test User",
        "first_name": "Test",
        "last_name": "User",
        "password": "hashed_password_here",
        "user_category": "Tenant"
    }
    
    success = db.add_to_collection("users", test_user)
    if success:
        print("\n✅ Test user created successfully")
        users = db.get_collection("users")
        print(f"Total users in database: {len(users)}")
    else:
        print("\n❌ Failed to create test user")
    
    # Final check
    print("\n" + "=" * 60)
    print("Final Database State")
    print("=" * 60)
    final_data = db.get_data()
    print(f"Total users: {len(final_data.get('users', []))}")
    print(f"Total buildings: {len(final_data.get('buildings', []))}")
    print(f"Total properties: {len(final_data.get('properties', []))}")

if __name__ == "__main__":
    test_database()