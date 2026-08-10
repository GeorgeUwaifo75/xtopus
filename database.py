import requests
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import os
from dotenv import load_dotenv
import logging
import time

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        # Correct API endpoint for JSONBinBro
        self.api_endpoint = os.getenv('JSONBIN_API_ENDPOINT', 'https://jsonbinbro.onrender.com/api')
        self.api_key = os.getenv('JSONBIN_API_KEY', 'admin_97375e28712d7627e7cea67c8c86d60d')
        self.bin_id = os.getenv('JSONBIN_BIN_ID', '6a511a2f02866d9b1850deec')
        self._initialized = False
        
    def _get_headers(self):
        return {
            'Content-Type': 'application/json',
        }
    
    def _get_url(self, endpoint: str = "") -> str:
        """Build URL with API key as query parameter"""
        base_url = f"{self.api_endpoint}/bins/{self.bin_id}{endpoint}"
        return f"{base_url}?api_key={self.api_key}"
    
    def get_data(self) -> Dict[str, Any]:
        """Fetch all data from JSONBin"""
        try:
            url = self._get_url()
            logger.info(f"Fetching data from: {url}")
            
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"API Response received")
                
                # CRITICAL FIX: JSONBinBro stores data in 'data' field
                # The response has a 'data' field that contains our actual data
                data = result.get('data', {})
                
                # If data is None or empty, initialize with empty structure
                if data is None or not data:
                    logger.warning("Data is null or empty, initializing...")
                    data = self._get_empty_data_structure()
                    # Save the initialized data
                    self.update_data(data)
                else:
                    # Ensure all collections exist
                    collections = ["users", "buildings", "properties", "tenants", 
             			   "payments", "complaints", "chats", "agreements", "agents", 
             			   "notifications", "tenant_requests"]  # Add notifications and tenant_requests
                    for col in collections:
                        if col not in data:
                            data[col] = []
                
                return data
            elif response.status_code == 404:
                logger.warning("Bin not found, creating new data structure")
                data = self._get_empty_data_structure()
                self.update_data(data)
                return data
            else:
                logger.error(f"API returned status {response.status_code}: {response.text}")
                return self._get_empty_data_structure()
                
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return self._get_empty_data_structure()
    
    def _get_empty_data_structure(self) -> Dict[str, Any]:
        """Return empty data structure"""
        return {
            "users": [],
            "buildings": [],
            "properties": [],
            "tenants": [],
            "payments": [],
            "complaints": [],
            "chats": [],
            "agreements": [],
            "agents": [],
            "notifications": [],
            "tenant_requests": [],
            "expenses": [],
            "chat_messages": [],  # Added
            "transactions": []    # Added
            
        }
        
    def update_data(self, data: Dict[str, Any]) -> bool:
        """Update data in JSONBin"""
        try:
            url = self._get_url()
            logger.info(f"Updating data at: {url}")
            
            # Ensure all collections exist
            collections = ["users", "buildings", "properties", "tenants", 
             	           "payments", "complaints", "chats", "agreements", "agents", 
             	           "notifications", "tenant_requests", "expenses", 
                           "chat_messages", "transactions"]  

            for col in collections:
                if col not in data:
                    data[col] = []
            
            # CRITICAL FIX: JSONBinBro requires the data to be wrapped in a "data" field
            # This is what worked in Approach 2
            wrapped_data = {"data": data}
            
            response = requests.put(
                url,
                headers=self._get_headers(),
                json=wrapped_data,  # Send wrapped data
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                # Check if data was actually saved
                if result.get('data') is not None:
                    logger.info("Data updated successfully")
                    return True
                else:
                    logger.error(f"Data was not saved properly: {result}")
                    return False
            else:
                logger.error(f"Failed to update data: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating data: {e}")
            return False
    
    def get_collection(self, collection_name: str) -> List[Dict[str, Any]]:
        """Get a specific collection from the database"""
        data = self.get_data()
        return data.get(collection_name, [])
    
    def add_to_collection(self, collection_name: str, item: Dict[str, Any]) -> bool:
        """Add an item to a collection"""
        data = self.get_data()
        if collection_name not in data:
            data[collection_name] = []
        
        # Generate ID if not present
        if '_id' not in item:
            item['_id'] = f"{collection_name}_{int(datetime.now().timestamp())}_{int(time.time() * 1000)}"
        
        # Add timestamps if not present
        if 'created_at' not in item:
            item['created_at'] = datetime.now().isoformat()
        if 'updated_at' not in item:
            item['updated_at'] = datetime.now().isoformat()
        
        data[collection_name].append(item)
        return self.update_data(data)
    
    def update_collection_item(self, collection_name: str, item_id: str, updates: Dict[str, Any]) -> bool:
        """Update an item in a collection"""
        data = self.get_data()
        collection = data.get(collection_name, [])
        
        for idx, item in enumerate(collection):
            if item.get('_id') == item_id or item.get('id') == item_id:
                updates['updated_at'] = datetime.now().isoformat()
                collection[idx].update(updates)
                return self.update_data(data)
        
        return False
    
    def delete_collection_item(self, collection_name: str, item_id: str) -> bool:
        """Delete an item from a collection"""
        data = self.get_data()
        collection = data.get(collection_name, [])
        
        collection = [item for item in collection 
                     if item.get('_id') != item_id and item.get('id') != item_id]
        data[collection_name] = collection
        
        return self.update_data(data)
    
    def query_collection(self, collection_name: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Query a collection with a filter"""
        collection = self.get_collection(collection_name)
        results = []
        
        for item in collection:
            match = True
            for key, value in query.items():
                if key in item and item[key] != value:
                    match = False
                    break
            if match:
                results.append(item)
        
        return results
    
    def find_one(self, collection_name: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find first matching item in a collection"""
        results = self.query_collection(collection_name, query)
        return results[0] if results else None
    
    def init_super_admin(self):
        """Initialize Super Admin user if it doesn't exist"""
        if self._initialized:
            return
            
        try:
            from security import security
            
            # Get current users directly
            data = self.get_data()
            users = data.get("users", [])
            logger.info(f"Current users in database: {len(users)}")
            
            # Check if Super Admin exists
            super_admin_exists = False
            for user in users:
                if user.get("user_category") == "Super Administrator" and user.get("user_id") == "SuperAdmin01":
                    super_admin_exists = True
                    logger.info("Super Admin user already exists")
                    break
            
            if not super_admin_exists:
                logger.info("Creating Super Admin user...")
                
                # Create Super Admin user
                super_admin = {
                    "_id": "super_admin_001",
                    "id": "super_admin_001",
                    "user_id": "SuperAdmin01",
                    "username": "Super Administrator",
                    "email": "superadmin@xtopus.com",
                    "password": security.hash_password("Kronosbase456@"),
                    "first_name": "Super",
                    "last_name": "Admin",
                    "user_category": "Super Administrator",
                    "activity_status": "Active",
                    "payment_status": "paid",
                    "profile_photo": None,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                
                # Get current data and add user
                data = self.get_data()
                if "users" not in data:
                    data["users"] = []
                data["users"].append(super_admin)
                
                success = self.update_data(data)
                if success:
                    logger.info("✅ Super Admin user created successfully")
                else:
                    logger.error("❌ Failed to create Super Admin user")
            else:
                logger.info("✅ Super Admin user already exists")
                
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Error initializing Super Admin: {e}")
            import traceback
            traceback.print_exc()

# Singleton instance
db = Database()

# Initialize Super Admin on startup
try:
    db.init_super_admin()
except Exception as e:
    logger.error(f"Failed to initialize Super Admin: {e}")
    import traceback
    traceback.print_exc()