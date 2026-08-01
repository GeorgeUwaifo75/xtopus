from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime
import logging
import uuid
import os
import requests
import firebase_admin
from firebase_admin import credentials, storage, initialize_app
from firebase_admin import auth as firebase_auth
import tempfile
import json
import base64

router = APIRouter()
logger = logging.getLogger(__name__)

from database import db
from security import security
from models.user import UserCategory

 # Firebase Configuration from .env
FIREBASE_API_KEY = os.getenv('FIREBASE_API_KEY', 'AIzaSyBj9wQ04hnfPjowVvEa_yf8_Fq3VXVaH5I')
FIREBASE_AUTH_DOMAIN = os.getenv('FIREBASE_AUTH_DOMAIN', 'giteksolhub-project.firebaseapp.com')
FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID', 'giteksolhub-project')
FIREBASE_STORAGE_BUCKET = os.getenv('FIREBASE_STORAGE_BUCKET', 'giteksolhub-project.firebasestorage.app')
FIREBASE_MESSAGING_SENDER_ID = os.getenv('FIREBASE_MESSAGING_SENDER_ID', '917911843059')
FIREBASE_APP_ID = os.getenv('FIREBASE_APP_ID', '1:917911843059:web:0aa2438be6605d1f400786')


# EmailJS Configuration
EMAILJS_SERVICE_ID = os.getenv('EMAILJS_SERVICE_ID', 'service_78wp8b9')
EMAILJS_TEMPLATE_ID = os.getenv('EMAILJS_TEMPLATE_ID', 'template_06fjijo')
EMAILJS_PUBLIC_KEY = os.getenv('EMAILJS_PUBLIC_KEY', 'VGj6eL5SaKXRW2fIi')
EMAILJS_PRIVATE_KEY = os.getenv('EMAILJS_PRIVATE_KEY', 'oogPO4beeg5UpY1k-Y-UA')
EMAILJS_API_URL = 'https://api.emailjs.com/api/v1.0/email/send'


# # Initialize Firebase
# try:
#     try:
#         firebase_admin.get_app()
#         logger.info("Firebase already initialized")
#     except ValueError:
#         firebase_cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH', 'firebase-credentials.json')
#         if os.path.exists(firebase_cred_path):
#             cred = credentials.Certificate(firebase_cred_path)
#             firebase_admin.initialize_app(cred, {
#                 'storageBucket': FIREBASE_STORAGE_BUCKET
#             })
#             logger.info(f"Firebase initialized successfully")
#         else:
#             private_key = os.getenv('FIREBASE_PRIVATE_KEY', '')
#             if private_key:
#                 cred = credentials.Certificate({
#                     "type": "service_account",
#                     "project_id": FIREBASE_PROJECT_ID,
#                     "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID', ''),
#                     "private_key": private_key.replace('\\n', '\n'),
#                     "client_email": os.getenv('FIREBASE_CLIENT_EMAIL', ''),
#                     "client_id": os.getenv('FIREBASE_CLIENT_ID', ''),
#                     "auth_uri": "https://accounts.google.com/o/oauth2/auth",
#                     "token_uri": "https://oauth2.googleapis.com/token",
#                     "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
#                     "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL', '')
#                 })
#                 firebase_admin.initialize_app(cred, {
#                     'storageBucket': FIREBASE_STORAGE_BUCKET
#                 })
#                 logger.info(f"Firebase initialized successfully")
#             else:
#                 logger.warning("No Firebase credentials found.")
# except Exception as e:
#     logger.error(f"Firebase initialization error: {e}")

# ============================================
# FIREBASE INITIALIZATION (with Base64 support)
# ============================================



def initialize_firebase():
    """Initialize Firebase from environment variables"""
    try:
        # Check if Firebase is already initialized
        try:
            firebase_admin.get_app()
            logger.info("Firebase already initialized")
            return
        except ValueError:
            pass
        
        # Try Base64 encoded credentials first (for Render)
        firebase_cred_base64 = os.getenv('FIREBASE_CREDENTIALS_BASE64')
        if firebase_cred_base64:
            try:
                cred_json = base64.b64decode(firebase_cred_base64).decode('utf-8')
                cred_dict = json.loads(cred_json)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred, {
                    'storageBucket': FIREBASE_STORAGE_BUCKET
                })
                logger.info("✅ Firebase initialized from Base64 credentials")
                return
            except Exception as e:
                logger.error(f"❌ Failed to initialize Firebase from Base64: {e}")
        
        # Try file-based initialization
        firebase_cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH', 'firebase-credentials.json')
        if os.path.exists(firebase_cred_path):
            cred = credentials.Certificate(firebase_cred_path)
            firebase_admin.initialize_app(cred, {
                'storageBucket': FIREBASE_STORAGE_BUCKET
            })
            logger.info(f"✅ Firebase initialized from file: {firebase_cred_path}")
            return
        
        # Try individual environment variables
        private_key = os.getenv('FIREBASE_PRIVATE_KEY', '')
        if private_key:
            cred = credentials.Certificate({
                "type": "service_account",
                "project_id": FIREBASE_PROJECT_ID,
                "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID', ''),
                "private_key": private_key.replace('\\n', '\n'),
                "client_email": os.getenv('FIREBASE_CLIENT_EMAIL', ''),
                "client_id": os.getenv('FIREBASE_CLIENT_ID', ''),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL', '')
            })
            firebase_admin.initialize_app(cred, {
                'storageBucket': FIREBASE_STORAGE_BUCKET
            })
            logger.info("✅ Firebase initialized from environment variables")
            return
        
        logger.warning("❌ No Firebase credentials found.")
        
    except Exception as e:
        logger.error(f"❌ Firebase initialization error: {e}")

# Call the function
initialize_firebase()



# Allowed image types
ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/jpg']
MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_PHOTOS = 4

def upload_to_firebase(file: UploadFile, folder: str = "buildings") -> str:
    try:
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        filename = f"{folder}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{file_extension}"
        content = file.file.read()
        bucket = storage.bucket()
        blob = bucket.blob(filename)
        blob.upload_from_string(content, content_type=file.content_type)
        blob.make_public()
        return blob.public_url
    except Exception as e:
        logger.error(f"Failed to upload to Firebase: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")

def filter_empty_uploads(photos: Optional[List[UploadFile]]) -> List[UploadFile]:
    """Browsers submit a file <input> as an empty part (filename='') when the
    user leaves it untouched, rather than omitting it entirely. Without this
    filter, edit forms that only touch text fields still send a bogus 'photo'
    that fails validation and gets misreported as a 500."""
    if not photos:
        return []
    return [p for p in photos if p.filename]


def validate_photos(photos: List[UploadFile]) -> None:
    if not photos:
        return
    if len(photos) > MAX_PHOTOS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_PHOTOS} photos allowed")
    for photo in photos:
        if photo.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {photo.content_type}")
        content = photo.file.read(MAX_IMAGE_SIZE + 1)
        photo.file.seek(0)
        if len(content) > MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail=f"File too large: {photo.filename}")

# In admin.py, update the send_emailjs_notification function:

def send_emailjs_notification(to_email: str, subject: str, body: str, template_params: dict = None) -> bool:
    try:
        if not all([EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, EMAILJS_PUBLIC_KEY]):
            logger.warning("EmailJS credentials not configured.")
            return False
        
        params = {
            'service_id': EMAILJS_SERVICE_ID,
            'template_id': EMAILJS_TEMPLATE_ID,
            'user_id': EMAILJS_PUBLIC_KEY,
            'template_params': {
                'seller_email': to_email,
                'to_name': 'User',
                'name': 'Xtopus Property Management',
                'email': 'geocorpsys@gmail.com',
                'message': body,
                'subject': subject,
                'product_name': 'Property'  # ← Default value if not provided
            }
        }
        
        if template_params:
            for key, value in template_params.items():
                if key in ['seller_email', 'to_name', 'name', 'email', 'message', 'subject', 'product_name']:
                    params['template_params'][key] = value
                else:
                    params['template_params'][key] = value
        
        response = requests.post(
            EMAILJS_API_URL,
            json=params,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Email sent successfully to {to_email}")
            return True
        else:
            logger.error(f"❌ EmailJS Error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ EmailJS Exception: {e}")
        return False
    
def create_notification(user_id: str, notification_type: str, message: str, related_data: dict = None):
    data = db.get_data()
    if "notifications" not in data:
        data["notifications"] = []
    
    notification = {
        "_id": f"notif_{int(datetime.now().timestamp())}_{user_id}_{uuid.uuid4().hex[:6]}",
        "user_id": user_id,
        "type": notification_type,
        "message": message,
        "related_data": related_data or {},
        "read": False,
        "created_at": datetime.now().isoformat()
    }
    data["notifications"].append(notification)
    db.update_data(data)
    return True


def get_current_user(request: Request):
    """Get current user from session token"""
    token = request.cookies.get("session_token")
    if not token:
        return None
    user_data = security.get_current_user(token)
    if not user_data:
        return None
    return user_data




# ============================================
# GET USERS FOR DROPDOWN (Fixed for Sub-Admins & Agents)
# ============================================
@router.get("/get_users_for_dropdown")
async def get_users_for_dropdown(request: Request):
    """Get regular users who are NOT assigned as tenants for dropdown selection"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Check if user has permission to assign tenants
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "You do not have permission to assign tenants"}
            )
        
        all_users = db.get_collection("users")
        available_users = []
        
        for user in all_users:
            user_category = user.get("user_category", "User")
            tenant_status = user.get("tenant_status", "")
            
            # Skip users who are already tenants or pending
            if user_category == "Tenant" or tenant_status in ["pending", "active", "pending_payment"]:
                continue
            
            # Skip admin roles (but allow Agents and Sub-Admins to see regular users)
            # Regular users have category "User"
            if user_category not in ["User"]:
                continue
            
            available_users.append({
                "user_id": user.get("user_id"),
                "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                "email": user.get("email")
            })
        
        return JSONResponse({
            "success": True,
            "users": available_users
        })
        
    except Exception as e:
        logger.error(f"Error getting users for dropdown: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# REQUEST TENANT ASSIGNMENT (Agent/Sub-Admin/Admin)
# ============================================
@router.post("/request_tenant_assignment")
async def request_tenant_assignment(request: Request):
    """Agent, Sub-Administrator, or Administrator requests tenant assignment for a user"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Check if user has permission to request tenant assignments
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "You do not have permission to request tenant assignments"}
            )
        
        body = await request.json()
        target_user_id = body.get("user_id")
        property_id = body.get("property_id")
        rental_start_date = body.get("rental_start_date")
        rental_end_date = body.get("rental_end_date")
        
        if not target_user_id or not property_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "User ID and Property ID are required"}
            )
        
        # Find target user
        users = db.get_collection("users")
        target_user = None
        for u in users:
            if u.get("user_id") == target_user_id:
                target_user = u
                break
        
        if not target_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "User not found"}
            )
        
        # Check if user is already a tenant
        if target_user.get("user_category") == "Tenant" or target_user.get("tenant_status") in ["active", "pending", "pending_payment"]:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "User is already a tenant or has a pending request"}
            )
        
        
        # After getting current_user, add this usage check:
        user_id = current_user.get("user_id")
        payment_status = current_user.get("payment_status", "free")
        
        # Count existing tenants assigned by this user
        users = db.get_collection("users")
        existing_tenants = [u for u in users if u.get("tenant_assigned_by") == user_id and u.get("user_category") == "Tenant"]
        
        # Check if free user has reached limit
        if payment_status == "free" and len(existing_tenants) >= 1:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False, 
                    "detail": "Free plan users can only assign 1 tenant. Please upgrade your plan to assign more."
                }
            )
        
        
        # Find property
        properties = db.get_collection("properties")
        property_item = None
        for p in properties:
            if p.get("_id") == property_id or p.get("id") == property_id:
                property_item = p
                break
        
        if not property_item:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Property not found"}
            )
        
        # Check if property is available
        if not property_item.get("available", True):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Property is not available"}
            )
        
        # Create tenant request
        request_id = f"tenant_req_{int(datetime.now().timestamp())}"
        
        # Update user with pending status
        target_user["tenant_status"] = "pending"
        target_user["assigned_property_id"] = property_id
        target_user["assigned_building_id"] = property_item.get("building_id")
        target_user["tenant_assigned_by"] = current_user.get("user_id")
        target_user["tenant_assigned_at"] = datetime.now().isoformat()
        target_user["needs_approval"] = True
        target_user["request_id"] = request_id
        # Keep user_category as "User" until approved
        target_user["updated_at"] = datetime.now().isoformat()
        
        # Save user update
        data = db.get_data()
        for i, u in enumerate(data["users"]):
            if u.get("user_id") == target_user_id:
                data["users"][i] = target_user
                break
        
        # Save the request with pending status (dates will be added at approval)
        if "tenant_requests" not in data:
            data["tenant_requests"] = []
        
        tenant_request = {
            "id": request_id,
            "user_id": target_user_id,
            "property_id": property_id,
            "requested_by": current_user.get("user_id"),
            "requested_at": datetime.now().isoformat(),
            "status": "pending",
            "user_name": f"{target_user.get('first_name', '')} {target_user.get('last_name', '')}".strip() or target_user_id,
            "property_name": property_item.get("name"),
            "property_price": property_item.get("price", 0)
        }
        
        # Add rental dates if provided (optional at request time)
        if rental_start_date:
            tenant_request["rental_start_date"] = rental_start_date
        if rental_end_date:
            tenant_request["rental_end_date"] = rental_end_date
        
        data["tenant_requests"].append(tenant_request)
        
        success = db.update_data(data)
        
        if success:
            # Find all administrators (Super Admin and Administrators)
            admins = [u for u in users if u.get("user_category") in ["Super Administrator", "Administrator"]]
            
            # Also find the direct admin if the requester is a Sub-Administrator
            if current_user.get("user_category") == "Sub-Administrator":
                created_by = current_user.get("created_by")
                for u in users:
                    if u.get("user_id") == created_by and u.get("user_category") in ["Super Administrator", "Administrator"]:
                        if u not in admins:
                            admins.append(u)
            
            for admin in admins:
                create_notification(
                    admin.get("user_id"),
                    "tenant_request",
                    f"📋 New tenant request from {current_user.get('user_id')} for {target_user_id} - Property: {property_item.get('name')}",
                    {
                        "request_id": request_id,
                        "user_id": target_user_id,
                        "property_id": property_id,
                        "requested_by": current_user.get("user_id"),
                        "property_name": property_item.get("name")
                    }
                )
                
                # Send email to admins
               # In request_tenant_assignment function, update the email sending:

            email_body = f"""
            Hello {admin.get('first_name', 'Admin')},
            
            A new tenant assignment request needs your review.
            
            Details:
            - User: {target_user_id} ({target_user.get('first_name', '')} {target_user.get('last_name', '')})
            - Property: {property_item.get('name')}
            - Building: {property_item.get('building_name', 'Unknown')}
            - Requested by: {current_user.get('user_id')}
            
            Please login to review and approve or reject this request. You will need to set the rental start and end dates.
            
            Regards,
            Xtopus Team
            """
            
            # Add template_params with product_name
            template_params = {
                'seller_email': admin.get("email"),
                'to_name': admin.get('first_name', 'Admin'),
                'name': 'Xtopus Property Management',
                'email': 'geocorpsys@gmail.com',
                'message': email_body,
                'subject': "Xtopus - Tenant Assignment Request",
                'product_name': property_item.get('name')  # ← ADD THIS
            }
            
            send_emailjs_notification(
                admin.get("email"),
                "Xtopus - Tenant Assignment Request",
                email_body,
                template_params
            )
            # Notify the requesting agent/sub-admin
            create_notification(
                current_user.get("user_id"),
                "tenant_request_submitted",
                f"Your tenant request for {target_user_id} has been submitted. Awaiting administrator approval.",
                {
                    "request_id": request_id,
                    "user_id": target_user_id,
                    "property_name": property_item.get("name")
                }
            )
            
            # Notify the user being assigned
            create_notification(
                target_user_id,
                "tenant_request_submitted",
                f"Your tenant request for '{property_item.get('name')}' has been submitted by {current_user.get('user_id')}. Awaiting approval.",
                {
                    "request_id": request_id,
                    "property_name": property_item.get("name"),
                    "requested_by": current_user.get("user_id")
                }
            )
            
            return JSONResponse({
                "success": True,
                "message": f"Tenant request submitted for {target_user_id}. Awaiting Administrator approval.",
                "request_id": request_id
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to submit tenant request"}
            )
            
    except Exception as e:
        logger.error(f"Error requesting tenant assignment: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )



# ============================================
# GET USERS FOR TENANT DROPDOWN (Complete Fix)
# ============================================
@router.get("/get_users_for_tenant")
async def get_users_for_tenant(request: Request):
    """Get regular users (non-tenants) for tenant assignment dropdown"""
    try:
        # Get current user
        current_user = get_current_user(request)
        if not current_user:
            logger.error("No current user found")
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Check if user has permission to assign tenants
        user_category = current_user.get("user_category", "")
        logger.info(f"Current user category: {user_category}")
        
        if user_category not in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
            logger.warning(f"User {current_user.get('user_id')} does not have permission to assign tenants")
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "You do not have permission to assign tenants"}
            )
        
        # Get all users
        all_users = db.get_collection("users")
        logger.info(f"Total users in database: {len(all_users)}")
        
        available_users = []
        
        for user in all_users:
            user_id = user.get("user_id")
            user_cat = user.get("user_category", "User")
            tenant_status = user.get("tenant_status", "")
            
            # Log for debugging
            logger.debug(f"Checking user: {user_id}, category: {user_cat}, tenant_status: {tenant_status}")
            
            # Skip users who are already tenants or have pending requests
            if user_cat == "Tenant" or tenant_status in ["pending", "active", "pending_payment"]:
                logger.debug(f"Skipping {user_id}: Already a tenant or pending")
                continue
            
            # Skip all admin roles: Super Administrator, Administrator, Sub-Administrator, Agent
            if user_cat in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
                logger.debug(f"Skipping {user_id}: Admin role")
                continue
            
            # Skip if user is the current user
            if user_id == current_user.get("user_id"):
                logger.debug(f"Skipping {user_id}: Current user")
                continue
            
            # This is a regular user (category "User") - add to available list
            logger.info(f"Adding regular user: {user_id}")
            available_users.append({
                "user_id": user_id,
                "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user_id,
                "email": user.get("email", "")
            })
        
        logger.info(f"Found {len(available_users)} available regular users")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "users": available_users,
                "count": len(available_users)
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting users for tenant: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

    
# ============================================
# GET PENDING TENANT REQUESTS (For Admins)
# ============================================
@router.get("/get_tenant_requests")
async def get_tenant_requests(request: Request):
    """Get all pending tenant requests for administrators"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only Administrators can view tenant requests"}
            )
        
        data = db.get_data()
        requests_list = data.get("tenant_requests", [])
        
        # Filter pending requests
        pending_requests = [r for r in requests_list if r.get("status") == "pending"]
        
        # Add user details to each request
        users = db.get_collection("users")
        for req in pending_requests:
            for u in users:
                if u.get("user_id") == req.get("user_id"):
                    req["user_email"] = u.get("email")
                    req["user_full_name"] = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                    break
            
            # Add requester details
            for u in users:
                if u.get("user_id") == req.get("requested_by"):
                    req["requested_by_name"] = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("user_id")
                    req["requested_by_email"] = u.get("email")
                    break
        
        return JSONResponse({
            "success": True,
            "requests": pending_requests,
            "count": len(pending_requests)
        })
        
    except Exception as e:
        logger.error(f"Error getting tenant requests: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET ALL BUILDINGS (For Management)
# ============================================
@router.get("/get_all_buildings")
async def get_all_buildings(request: Request):
    """Get all buildings for management"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        buildings = db.get_collection("buildings")
        
        # If Administrator, only show buildings they created
        if category == "Administrator":
            buildings = [b for b in buildings if b.get("created_by") == current_user.get("user_id")]
        
        return JSONResponse({
            "success": True,
            "buildings": buildings,
            "count": len(buildings)
        })
        
    except Exception as e:
        logger.error(f"Error getting buildings: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET ALL PROPERTIES WITH OCCUPANT NAMES (For Management)
# ============================================
@router.get("/get_all_properties_with_occupants")
async def get_all_properties_with_occupants(request: Request):
    """Get all properties for management with occupant names"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        properties = db.get_collection("properties")
        users = db.get_collection("users")
        
        # Build a lookup dictionary for user names
        user_name_map = {}
        for user in users:
            user_id = user.get("user_id")
            if user_id:
                full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                user_name_map[user_id] = full_name or user_id
        
        # If Administrator, only show properties they created
        if category == "Administrator":
            properties = [p for p in properties if p.get("created_by") == current_user.get("user_id")]
        
        # Add occupant names to each property
        for prop in properties:
            occupied_by = prop.get("occupied_by")
            if occupied_by and occupied_by in user_name_map:
                prop["occupant_name"] = user_name_map[occupied_by]
            elif occupied_by:
                prop["occupant_name"] = occupied_by  # Fallback to user_id
        
        return JSONResponse({
            "success": True,
            "properties": properties,
            "count": len(properties)
        })
        
    except Exception as e:
        logger.error(f"Error getting properties with occupants: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# CREATE AGENT (Fixed)
# ============================================
@router.post("/create_agent")
async def create_agent(request: Request):
    """Create an Agent under the current Administrator"""
    try:
        # Get current user
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Check if user is Super Admin or Admin
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only Administrators can create Agents"}
            )
        
        # Get request data
        data = await request.json()
        user_id = data.get("user_id")
        email = data.get("email")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        password = data.get("password")
        username = data.get("username", user_id)
        
        # Validate required fields
        if not all([user_id, email, first_name, last_name, password]):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Missing required fields"}
            )
        
        # Check if user already exists
        existing_users = db.query_collection("users", {"user_id": user_id})
        if existing_users:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": f"User ID '{user_id}' already exists"}
            )
        
        # Check if email already exists
        existing_emails = db.query_collection("users", {"email": email})
        if existing_emails:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": f"Email '{email}' already registered"}
            )
        
        # Hash password
        hashed_password = security.hash_password(password)
        
        # Create Agent user
        new_user = {
            "_id": f"agent_{int(datetime.now().timestamp())}",
            "user_id": user_id,
            "username": username,
            "email": email,
            "password": hashed_password,
            "first_name": first_name,
            "last_name": last_name,
            "user_category": "Agent",
            "activity_status": "Active",
            "payment_status": "paid",
            "created_by": current_user.get("user_id"),
            "created_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "profile_photo": None
        }
        new_user["payment_status"] = current_user.get("payment_status", "free")  
        
        success = db.add_to_collection("users", new_user)
        
        if success:
            # Add to creator's agents list
            users = db.get_collection("users")
            for u in users:
                if u.get("user_id") == current_user.get("user_id"):
                    if "agents" not in u:
                        u["agents"] = []
                    if user_id not in u["agents"]:
                        u["agents"].append(user_id)
                    db.update_collection_item("users", u.get("_id"), u)
                    break
            
            return JSONResponse(
                status_code=201,
                content={
                    "success": True,
                    "message": f"Agent '{user_id}' created successfully",
                    "user": {
                        "user_id": user_id,
                        "email": email,
                        "first_name": first_name,
                        "last_name": last_name,
                        "user_category": "Agent"
                    }
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to save user to database"}
            )
            
    except Exception as e:
        logger.error(f"Error creating Agent: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )
# ============================================
# CREATE SUB-ADMINISTRATOR (Fixed - supports both Admin and Sub-Admin)
# ============================================
@router.post("/create_sub_admin")
async def create_sub_admin(request: Request):
    """Create a Sub-Administrator or Administrator under the current Super Administrator"""
    try:
        # Get current user
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Check if user is Super Admin or Admin
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only Administrators can create Sub-Administrators"}
            )
        
        # Get request data
        data = await request.json()
        user_id = data.get("user_id")
        email = data.get("email")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        password = data.get("password")
        username = data.get("username", user_id)
        
        # Determine user category - Super Admin can create Administrators and Sub-Administrators
        # Admin can only create Sub-Administrators
        user_category = data.get("user_category", "Sub-Administrator")
        
        # If current user is Administrator, they can only create Sub-Administrators
        if category == "Administrator":
            user_category = "Sub-Administrator"
        # If current user is Super Administrator and category is not provided, default to Administrator
        elif category == "Super Administrator" and user_category == "Sub-Administrator":
            # If Super Admin explicitly wants Sub-Admin, allow it
            pass
        
        # Get permissions
        permissions = data.get("permissions", {})
        can_create_agents = permissions.get("can_create_agents", False)
        can_create_buildings = permissions.get("can_create_buildings", False)
        can_create_properties = permissions.get("can_create_properties", False)
        can_manage_tenants = permissions.get("can_manage_tenants", True)
        
        # Validate required fields
        if not all([user_id, email, first_name, last_name, password]):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Missing required fields"}
            )
        
        # Check if user already exists
        existing_users = db.query_collection("users", {"user_id": user_id})
        if existing_users:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": f"User ID '{user_id}' already exists"}
            )
        
        # Check if email already exists
        existing_emails = db.query_collection("users", {"email": email})
        if existing_emails:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": f"Email '{email}' already registered"}
            )
        
        # Hash password
        hashed_password = security.hash_password(password)
        
        # Create user with appropriate category
        new_user = {
            "_id": f"user_{int(datetime.now().timestamp())}",
            "user_id": user_id,
            "username": username,
            "email": email,
            "password": hashed_password,
            "first_name": first_name,
            "last_name": last_name,
            "user_category": user_category,  # "Administrator" or "Sub-Administrator"
            "activity_status": "Active",
            "payment_status": "paid",
            "created_by": current_user.get("user_id"),
            "created_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "profile_photo": None,
            "permissions": {
                "can_create_agents": can_create_agents,
                "can_create_buildings": can_create_buildings,
                "can_create_properties": can_create_properties,
                "can_manage_tenants": can_manage_tenants
            }
        }
        
        new_user["payment_status"] = current_user.get("payment_status", "free")  
        
        success = db.add_to_collection("users", new_user)
        
        if success:
            # Add to creator's sub_admins list (if Sub-Admin) or admins list (if Admin)
           
            
            users = db.get_collection("users")
            for u in users:
                if u.get("user_id") == current_user.get("user_id"):
                    if user_category == "Administrator":
                        if "admins" not in u:
                            u["admins"] = []
                        if user_id not in u["admins"]:
                            u["admins"].append(user_id)
                    else:
                        if "sub_admins" not in u:
                            u["sub_admins"] = []
                        if user_id not in u["sub_admins"]:
                            u["sub_admins"].append(user_id)
                    db.update_collection_item("users", u.get("_id"), u)
                    break
            
            # Create notification for the admin
            create_notification(
                current_user.get("user_id"),
                "user_created",
                f"{user_category} '{user_id}' created successfully with permissions: Agents={can_create_agents}, Buildings={can_create_buildings}, Properties={can_create_properties}"
            )
            
            
            
            return JSONResponse(
                status_code=201,
                content={
                    "success": True,
                    "message": f"{user_category} '{user_id}' created successfully with configured permissions",
                    "user": {
                        "user_id": user_id,
                        "email": email,
                        "first_name": first_name,
                        "last_name": last_name,
                        "user_category": user_category,
                        "permissions": new_user["permissions"]
                    }
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to save user to database"}
            )
            
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )
    
# ============================================
# GET ALL PROPERTIES (For Management)
# ============================================
@router.get("/get_all_properties")
async def get_all_properties(request: Request):
    """Get all properties for management"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        properties = db.get_collection("properties")
        
        # If Administrator, only show properties they created
        if category == "Administrator":
            properties = [p for p in properties if p.get("created_by") == current_user.get("user_id")]
        
        return JSONResponse({
            "success": True,
            "properties": properties,
            "count": len(properties)
        })
        
    except Exception as e:
        logger.error(f"Error getting properties: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# DELETE BUILDING
# ============================================
@router.delete("/delete_building/{building_id}")
async def delete_building(request: Request, building_id: str):
    """Delete a building"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        # Find the building
        buildings = db.get_collection("buildings")
        building = None
        for b in buildings:
            if b.get("_id") == building_id or b.get("id") == building_id:
                building = b
                break
        
        if not building:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Building not found"}
            )
        
        # Check if user has permission to delete this building
        if category == "Administrator":
            if building.get("created_by") != current_user.get("user_id"):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "You can only delete buildings you created"}
                )
        
        # Check if building has properties
        properties = db.get_collection("properties")
        has_properties = False
        for p in properties:
            if p.get("building_id") == building_id or p.get("building_id") == building.get("id"):
                has_properties = True
                break
        
        if has_properties:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Cannot delete building with existing properties. Delete the properties first."}
            )
        
        # Delete the building
        success = db.delete_collection_item("buildings", building_id)
        
        if success:
            return JSONResponse({
                "success": True,
                "message": f"Building '{building.get('name')}' deleted successfully"
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to delete building"}
            )
            
    except Exception as e:
        logger.error(f"Error deleting building: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# DELETE PROPERTY
# ============================================
@router.delete("/delete_property/{property_id}")
async def delete_property(request: Request, property_id: str):
    """Delete a property"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        # Find the property
        properties = db.get_collection("properties")
        property_item = None
        for p in properties:
            if p.get("_id") == property_id or p.get("id") == property_id:
                property_item = p
                break
        
        if not property_item:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Property not found"}
            )
        
        # Check if user has permission to delete this property
        if category == "Administrator":
            if property_item.get("created_by") != current_user.get("user_id"):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "You can only delete properties you created"}
                )
        
        # Check if property is occupied
        if property_item.get("occupied_by"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Cannot delete an occupied property. The tenant must be removed first."}
            )
        
        # Delete the property
        success = db.delete_collection_item("properties", property_id)
        
        if success:
            return JSONResponse({
                "success": True,
                "message": f"Property '{property_item.get('name')}' deleted successfully"
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to delete property"}
            )
            
    except Exception as e:
        logger.error(f"Error deleting property: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET ADMIN DASHBOARD DATA (For My Team module)
# ============================================
@router.get("/get_admin_dashboard_data")
async def get_admin_dashboard_data(request: Request):
    """Get dashboard data including team members for admins"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator", "Sub-Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        users = db.get_collection("users")
        
        # Get sub-admins created by this user
        sub_admins = []
        for user in users:
            if user.get("user_category") == "Sub-Administrator":
                created_by = user.get("created_by")
                if created_by == current_user.get("user_id"):
                    sub_admins.append({
                        "user_id": user.get("user_id"),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                        "email": user.get("email"),
                        "permissions": user.get("permissions", {})
                    })
        
        # Get agents created by this user
        agents = []
        for user in users:
            if user.get("user_category") == "Agent":
                created_by = user.get("created_by")
                if created_by == current_user.get("user_id"):
                    agents.append({
                        "user_id": user.get("user_id"),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                        "email": user.get("email")
                    })
        
        # For Super Admin, also get all sub-admins and agents (not just created by them)
        if category == "Super Administrator":
            # Get all sub-admins
            all_sub_admins = []
            for user in users:
                if user.get("user_category") == "Sub-Administrator":
                    all_sub_admins.append({
                        "user_id": user.get("user_id"),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                        "email": user.get("email"),
                        "permissions": user.get("permissions", {})
                    })
            sub_admins = all_sub_admins
            
            # Get all agents
            all_agents = []
            for user in users:
                if user.get("user_category") == "Agent":
                    all_agents.append({
                        "user_id": user.get("user_id"),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                        "email": user.get("email")
                    })
            agents = all_agents
        
        return JSONResponse({
            "success": True,
            "sub_admins": sub_admins,
            "agents": agents,
            "counts": {
                "sub_admins": len(sub_admins),
                "agents": len(agents)
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting admin dashboard data: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET TENANTS UNDER ADMIN (For Tenants Report)
# ============================================
@router.get("/get_tenants_under_admin")
async def get_tenants_under_admin(request: Request):
    """Get all tenants under this admin's management"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator", "Sub-Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        users = db.get_collection("users")
        properties = db.get_collection("properties")
        
        tenants_list = []
        today = datetime.now().date()
        
        for user in users:
            # Only include tenants
            if user.get("user_category") == "Tenant" and user.get("tenant_status") == "active":
                assigned_by = user.get("tenant_assigned_by")
                
                # Check if this tenant is under this admin's management
                include = False
                if category == "Super Administrator":
                    include = True
                elif category == "Administrator":
                    # Check if assigned by this admin or their sub-admins
                    include = (assigned_by == current_user.get("user_id"))
                    if not include:
                        # Check if assigned by a sub-admin of this admin
                        sub_admins = current_user.get("sub_admins", [])
                        if assigned_by in sub_admins:
                            include = True
                elif category == "Sub-Administrator":
                    include = (assigned_by == current_user.get("user_id"))
                
                if include:
                    rental_end = user.get("rental_end_date")
                    days_remaining = None
                    status = "active"
                    
                    if rental_end:
                        try:
                            end_date = datetime.fromisoformat(rental_end).date()
                            days_remaining = (end_date - today).days
                            if days_remaining < 0:
                                status = "overdue"
                            elif days_remaining <= 30:
                                status = "expiring_soon"
                        except:
                            pass
                    
                    # Get property info
                    property_info = None
                    property_id = user.get("assigned_property_id")
                    if property_id:
                        for p in properties:
                            if p.get("_id") == property_id or p.get("id") == property_id:
                                property_info = p
                                break
                    
                    tenants_list.append({
                        "user_id": user.get("user_id"),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                        "email": user.get("email"),
                        "phone": user.get("phone", ""),
                        "rental_start_date": user.get("rental_start_date"),
                        "rental_end_date": rental_end,
                        "days_remaining": days_remaining,
                        "status": status,
                        "property_name": property_info.get("name") if property_info else "Unknown",
                        "property_id": property_id,
                        "assigned_by": assigned_by,
                        "payment_status": user.get("payment_status", "pending"),
                        "rent_amount": user.get("rent_amount", 0)
                    })
        
        # Sort tenants by status (overdue first, then expiring soon, then active)
        status_order = {"overdue": 0, "expiring_soon": 1, "active": 2}
        tenants_list.sort(key=lambda x: status_order.get(x.get("status", "active"), 3))
        
        return JSONResponse({
            "success": True,
            "tenants": tenants_list,
            "count": len(tenants_list)
        })
        
    except Exception as e:
        logger.error(f"Error getting tenants under admin: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# APPROVE TENANT REQUEST (With Date Selection)
# ============================================
@router.post("/approve_tenant_request")
async def approve_tenant_request(request: Request):
    """Administrator approves or rejects a tenant request with rental dates"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only Administrators can approve tenant requests"}
            )
        
        body = await request.json()
        request_id = body.get("request_id")
        action = body.get("action")  # "approve" or "reject"
        rental_start_date = body.get("rental_start_date")
        rental_end_date = body.get("rental_end_date")
        
        if not request_id or not action:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Request ID and action are required"}
            )
        
        data = db.get_data()
        
        # Find the request
        request_item = None
        request_index = None
        for i, r in enumerate(data.get("tenant_requests", [])):
            if r.get("id") == request_id:
                request_item = r
                request_index = i
                break
        
        if not request_item:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Request not found"}
            )
        
        if request_item.get("status") != "pending":
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Request is no longer pending"}
            )
        
        target_user_id = request_item.get("user_id")
        requested_by = request_item.get("requested_by")
        property_id = request_item.get("property_id")
        
        # ----- FIX: Get property price from the actual property -----
        properties = db.get_collection("properties")
        property_item = None
        for p in properties:
            if p.get("_id") == property_id or p.get("id") == property_id:
                property_item = p
                break
        
        if not property_item:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Property not found"}
            )
        
        property_price = property_item.get("price", 0)
        property_name = property_item.get("name", "Unknown Property")
        # ------------------------------------------------------------
        
        # Find target user
        target_user = None
        target_index = None
        for i, u in enumerate(data["users"]):
            if u.get("user_id") == target_user_id:
                target_user = u
                target_index = i
                break
        
        if not target_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Target user not found"}
            )
        
        if action == "approve":
            # Validate dates for approval
            if not rental_start_date or not rental_end_date:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "detail": "Rental start date and end date are required for approval"}
                )
            
            try:
                start_date = datetime.fromisoformat(rental_start_date)
                end_date = datetime.fromisoformat(rental_end_date)
                if end_date <= start_date:
                    return JSONResponse(
                        status_code=400,
                        content={"success": False, "detail": "End date must be after start date"}
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "detail": "Invalid date format"}
                )
            
            # Update property availability
            for p in data["properties"]:
                if p.get("_id") == property_id or p.get("id") == property_id:
                    p["available"] = False
                    p["occupied_by"] = target_user_id
                    p["rental_start_date"] = rental_start_date
                    p["rental_end_date"] = rental_end_date
                    p["updated_at"] = datetime.now().isoformat()
                    break
            
            # Update user - Set user_category to "Tenant" and tenant_status to "pending_payment"
            target_user["user_category"] = "Tenant"
            target_user["tenant_status"] = "pending_payment"
            target_user["tenant_activated_by"] = current_user.get("user_id")
            target_user["tenant_activated_at"] = datetime.now().isoformat()
            target_user["activity_status"] = "Active"
            target_user["needs_approval"] = False
            target_user["assigned_property_id"] = property_id
            target_user["assigned_property_name"] = property_name  # Store property name
            target_user["rental_start_date"] = rental_start_date
            target_user["rental_end_date"] = rental_end_date
            target_user["rent_amount"] = property_price  # ----- FIX: Set rent amount from property price -----
            target_user["payment_status"] = "pending"
            target_user["updated_at"] = datetime.now().isoformat()
            
            # Update request status
            request_item["status"] = "approved"
            request_item["approved_by"] = current_user.get("user_id")
            request_item["approved_at"] = datetime.now().isoformat()
            request_item["rental_start_date"] = rental_start_date
            request_item["rental_end_date"] = rental_end_date
            request_item["property_price"] = property_price  # Store price in request too
            
            message = f"Tenant request for {target_user_id} approved by {current_user.get('user_id')}"
            
        elif action == "reject":
            # REVERT USER TO ORDINARY USER - Clean all tenant-related fields
            target_user["user_category"] = "User"
            target_user["tenant_status"] = None
            target_user["tenant_rejected_by"] = current_user.get("user_id")
            target_user["tenant_rejected_at"] = datetime.now().isoformat()
            target_user["needs_approval"] = False
            target_user["updated_at"] = datetime.now().isoformat()
            
            # Remove ALL tenant-related fields
            fields_to_remove = [
                "assigned_property_id", "assigned_building_id", 
                "tenant_assigned_by", "tenant_assigned_at",
                "tenant_activated_by", "tenant_activated_at",
                "rental_start_date", "rental_end_date", "request_id",
                "rent_amount", "assigned_property_name"
            ]
            for field in fields_to_remove:
                if field in target_user:
                    del target_user[field]
            
            # Update request status
            request_item["status"] = "rejected"
            request_item["rejected_by"] = current_user.get("user_id")
            request_item["rejected_at"] = datetime.now().isoformat()
            
            message = f"Tenant request for {target_user_id} rejected by {current_user.get('user_id')}"
        else:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Invalid action. Use 'approve' or 'reject'"}
            )
        
        # Save changes
        data["users"][target_index] = target_user
        data["tenant_requests"][request_index] = request_item
        success = db.update_data(data)
        
        if success:
            # Notify the agent who requested
            if requested_by:
                if action == "approve":
                    create_notification(
                        requested_by,
                        "tenant_request_approved",
                        f"✅ Your tenant request for {target_user_id} has been APPROVED by {current_user.get('user_id')}. The tenant can now make payment of ₦{property_price}.",
                        {
                            "request_id": request_id,
                            "user_id": target_user_id,
                            "property_name": property_name,
                            "rent_amount": property_price
                        }
                    )
                else:
                    create_notification(
                        requested_by,
                        "tenant_request_rejected",
                        f"❌ Your tenant request for {target_user_id} has been REJECTED by {current_user.get('user_id')}.",
                        {
                            "request_id": request_id,
                            "user_id": target_user_id
                        }
                    )
            
            # Notify the tenant
            if action == "approve":
                create_notification(
                    target_user_id,
                    "tenant_approved_payment_required",
                    f"🎉 Your tenant status has been approved by {current_user.get('user_id')}! Please make payment of ₦{property_price} to activate your tenancy.",
                    {
                        "property_id": property_id,
                        "property_name": property_name,
                        "rent_amount": property_price,
                        "rental_start": rental_start_date,
                        "rental_end": rental_end_date,
                        "payment_status": "pending"
                    }
                )
                
                # Send email to tenant
                email_body = f"""
Hello {target_user.get('first_name', 'Tenant')},

🎉 Congratulations! Your tenant request has been APPROVED by {current_user.get('user_id')}.

Rental Details:
- Property: {property_name}
- Rental Period: {rental_start_date} to {rental_end_date}
- Monthly Rent: ₦{property_price}

Please login to make your payment and complete the activation process.

Regards,
Xtopus Team
"""
                template_params = {
                    'seller_email': target_user.get("email"),
                    'to_name': target_user.get('first_name', 'Tenant'),
                    'name': 'Xtopus Property Management',
                    'email': 'geocorpsys@gmail.com',
                    'message': email_body,
                    'subject': "Xtopus - Tenant Request Approved - Payment Required",
                    'product_name': property_name  # ← ADD THIS
                }
                
                send_emailjs_notification(
                    target_user.get("email"),
                    "Xtopus - Tenant Request Approved - Payment Required",
                    email_body,
                    template_params
                )
            else:
                # Notify the user that their request was rejected
                create_notification(
                    target_user_id,
                    "tenant_rejected",
                    f"❌ Your tenant request has been rejected by {current_user.get('user_id')}. Your account has been reverted to a regular user."
                )
                
                # Send email to the rejected user
                email_body = f"""
Hello {target_user.get('first_name', 'User')},

Your tenant request has been REJECTED by {current_user.get('user_id')}.

Your account has been reverted to a regular user account.

If you have any questions, please contact support.

Regards,
Xtopus Team
"""
                template_params = {
                'seller_email': target_user.get("email"),
                'to_name': target_user.get('first_name', 'User'),
                'name': 'Xtopus Property Management',
                'email': 'geocorpsys@gmail.com',
                'message': email_body,
                'subject': "Xtopus - Tenant Request Rejected",
                'product_name': property_name if property_name else "Property"  # ← ADD THIS
            }
            
            send_emailjs_notification(
                target_user.get("email"),
                "Xtopus - Tenant Request Rejected",
                email_body,
                template_params
            )
            
            # If approved, also notify the property manager (if different from admin)
            if action == "approve":
                # Notify all admins about the approval
                admins = [u for u in data["users"] if u.get("user_category") in ["Super Administrator", "Administrator"]]
                for admin in admins:
                    if admin.get("user_id") != current_user.get("user_id"):
                        create_notification(
                            admin.get("user_id"),
                            "tenant_approved",
                            f"Tenant {target_user_id} was approved by {current_user.get('user_id')} for property '{property_name}'. Payment of ₦{property_price} pending.",
                            {
                                "user_id": target_user_id,
                                "property_name": property_name,
                                "approved_by": current_user.get("user_id"),
                                "rent_amount": property_price
                            }
                        )
            
            return JSONResponse({
                "success": True,
                "message": message,
                "request": request_item,
                "user": {
                    "user_id": target_user_id,
                    "user_category": target_user.get("user_category"),
                    "tenant_status": target_user.get("tenant_status"),
                    "rent_amount": target_user.get("rent_amount", 0)
                }
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to process tenant request"}
            )
            
    except Exception as e:
        logger.error(f"Error approving tenant request: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )
# ============================================
# INITIATE PAYMENT (Paystack)
# ============================================
@router.post("/initiate_payment")
async def initiate_payment(request: Request):
    """Initiate payment for tenant activation via Paystack"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        body = await request.json()
        user_id = body.get("user_id")
        property_id = body.get("property_id")
        amount = body.get("amount")
        email = body.get("email")
        callback_url = body.get("callback_url")
        
        if not user_id or not property_id or not amount or not email:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Missing required fields"}
            )
        
        # In production, integrate with Paystack API
        # For now, return a simulated payment reference
        payment_reference = f"PAY-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        
        return JSONResponse({
            "success": True,
            "payment_reference": payment_reference,
            "amount": amount,
            "email": email,
            "message": "Payment initiated successfully"
        })
        
    except Exception as e:
        logger.error(f"Error initiating payment: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# CONFIRM PAYMENT (Tenant notifies of payment)
# ============================================
@router.post("/confirm_payment_made")
async def confirm_payment_made(request: Request):
    """Tenant confirms payment has been made"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        body = await request.json()
        user_id = body.get("user_id")
        payment_reference = body.get("payment_reference")
        
        if not user_id or not payment_reference:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "User ID and payment reference are required"}
            )
        
        # Find the user
        users = db.get_collection("users")
        target_user = None
        for u in users:
            if u.get("user_id") == user_id:
                target_user = u
                break
        
        if not target_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "User not found"}
            )
        
        # Update user payment status
        target_user["payment_status"] = "pending_confirmation"
        target_user["payment_reference"] = payment_reference
        target_user["payment_confirmed_at"] = datetime.now().isoformat()
        target_user["payment_confirmed_by"] = current_user.get("user_id")
        
        success = db.update_collection_item("users", target_user.get("_id"), target_user)
        
        if success:
            # Notify all administrators
            admins = [u for u in users if u.get("user_category") in ["Super Administrator", "Administrator"]]
            for admin in admins:
                create_notification(
                    admin.get("user_id"),
                    "payment_confirmed_pending",
                    f"💰 Payment of ₦{target_user.get('rent_amount', 0)} has been confirmed by {user_id}. Waiting for admin verification.",
                    {
                        "user_id": user_id,
                        "payment_reference": payment_reference,
                        "amount": target_user.get("rent_amount", 0)
                    }
                )
            
            # Notify the agent who assigned this tenant
            assigned_by = target_user.get("tenant_assigned_by")
            if assigned_by:
                create_notification(
                    assigned_by,
                    "payment_confirmed",
                    f"💰 {user_id} has made payment of ₦{target_user.get('rent_amount', 0)}. Waiting for admin verification.",
                    {
                        "user_id": user_id,
                        "payment_reference": payment_reference
                    }
                )
            
            # Also notify the tenant
            create_notification(
                user_id,
                "payment_submitted",
                f"Your payment of ₦{target_user.get('rent_amount', 0)} has been submitted. Awaiting administrator confirmation.",
                {
                    "payment_reference": payment_reference
                }
            )
            
            return JSONResponse({
                "success": True,
                "message": "Payment confirmation submitted. Administrators will verify your payment."
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to confirm payment"}
            )
            
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# VERIFY PAYMENT AND ACTIVATE TENANT (Admin)
# ============================================
@router.post("/verify_payment_and_activate")
async def verify_payment_and_activate(request: Request):
    """Admin verifies payment and activates the tenant"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only Administrators can verify and activate"}
            )
        
        body = await request.json()
        user_id = body.get("user_id")
        payment_reference = body.get("payment_reference")
        transaction_id = body.get("transaction_id")
        
        if not user_id or not payment_reference:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "User ID and payment reference are required"}
            )
        
        # Find the user
        users = db.get_collection("users")
        target_user = None
        for u in users:
            if u.get("user_id") == user_id:
                target_user = u
                break
        
        if not target_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "User not found"}
            )
        
        # Update user to fully activated
        target_user["tenant_status"] = "active"
        target_user["payment_status"] = "paid"
        target_user["payment_verified_by"] = current_user.get("user_id")
        target_user["payment_verified_at"] = datetime.now().isoformat()
        target_user["tenant_activated_by"] = current_user.get("user_id")
        target_user["tenant_activated_at"] = datetime.now().isoformat()
        
        success = db.update_collection_item("users", target_user.get("_id"), target_user)
        
        if success:
            # Record payment
            payment_record = {
                "_id": f"pay_{int(datetime.now().timestamp())}",
                "user_id": user_id,
                "property_id": target_user.get("assigned_property_id"),
                "amount": target_user.get("rent_amount", 0),
                "payment_reference": payment_reference,
                "transaction_id": transaction_id,
                "status": "verified",
                "verified_by": current_user.get("user_id"),
                "verified_at": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat()
            }
            db.add_to_collection("payments", payment_record)
            
            # Update property
            properties = db.get_collection("properties")
            property_id = target_user.get("assigned_property_id")
            for p in properties:
                if p.get("_id") == property_id or p.get("id") == property_id:
                    p["payment_verified"] = True
                    p["payment_verified_at"] = datetime.now().isoformat()
                    db.update_collection_item("properties", p.get("_id"), p)
                    break
            
            # Notify the tenant
            create_notification(
                user_id,
                "tenant_activated",
                f"🎉 Your tenancy has been ACTIVATED! Welcome to your new home.",
                {
                    "property_id": target_user.get("assigned_property_id"),
                    "rental_start": target_user.get("rental_start_date"),
                    "rental_end": target_user.get("rental_end_date")
                }
            )
            
            # Notify the agent who assigned this tenant
            assigned_by = target_user.get("tenant_assigned_by")
            if assigned_by:
                create_notification(
                    assigned_by,
                    "tenant_activated",
                    f"🎉 {user_id} has been fully activated as a tenant by {current_user.get('user_id')}.",
                    {
                        "user_id": user_id,
                        "property_name": target_user.get("assigned_property_name", "Unknown Property")
                    }
                )
            
            # Notify all admins
            admins = [u for u in users if u.get("user_category") in ["Super Administrator", "Administrator"]]
            for admin in admins:
                if admin.get("user_id") != current_user.get("user_id"):
                    create_notification(
                        admin.get("user_id"),
                        "tenant_activated",
                        f"🎉 {user_id} has been activated as a tenant by {current_user.get('user_id')}.",
                        {
                            "user_id": user_id
                        }
                    )
            
            # Send email to tenant
            email_body = f"""
Hello {target_user.get('first_name', 'Tenant')},

🎉 Congratulations! Your tenancy has been ACTIVATED.

Property: {target_user.get('assigned_property_name', 'Property')}
Rental Period: {target_user.get('rental_start_date')} to {target_user.get('rental_end_date')}
Monthly Rent: ₦{target_user.get('rent_amount', 0)}

Your tenancy is now active. Welcome to your new home!

Regards,
Xtopus Team
"""
            template_params = {
                'seller_email': target_user.get("email"),
                'to_name': target_user.get('first_name', 'Tenant'),
                'name': 'Xtopus Property Management',
                'email': 'geocorpsys@gmail.com',
                'message': email_body,
                'subject': "Xtopus - Tenancy Activated",
                'product_name': target_user.get('assigned_property_name', 'Property')  # ← ADD THIS
            }
            
            send_emailjs_notification(
                target_user.get("email"),
                "Xtopus - Tenancy Activated",
                email_body,
                template_params
            )
            
            return JSONResponse({
                "success": True,
                "message": f"Tenant {user_id} activated successfully! Payment verified."
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to activate tenant"}
            )
            
    except Exception as e:
        logger.error(f"Error verifying payment and activating: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# DELETE USER - Complete Fix
# ============================================
@router.delete("/delete_user/{user_id}")
async def delete_user(request: Request, user_id: str):
    """Delete a user - only if they were created by the current user or are Super Admin"""
    try:
        # Get current user
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Check if user is Super Admin or Admin
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        # Find the user to delete
        users = db.get_collection("users")
        target_user = None
        target_index = -1
        
        for idx, user in enumerate(users):
            if user.get("user_id") == user_id:
                target_user = user
                target_index = idx
                break
        
        if not target_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": f"User '{user_id}' not found"}
            )
        
        # Prevent deleting Super Administrator
        if target_user.get("user_category") == "Super Administrator":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Cannot delete Super Administrator"}
            )
        
        # Prevent deleting own account
        if target_user.get("user_id") == current_user.get("user_id"):
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Cannot delete your own account"}
            )
        
        # If current user is Administrator (not Super Admin), check if they created this user
        if category == "Administrator":
            created_by = target_user.get("created_by")
            if created_by != current_user.get("user_id"):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "You can only delete users you created"}
                )
        
        # Get the user's _id for deletion
        user_id_to_delete = target_user.get("_id") or target_user.get("id")
        
        if not user_id_to_delete:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "User has no valid ID"}
            )
        
        # Delete the user using the database method
        success = db.delete_collection_item("users", user_id_to_delete)
        
        if success:
            logger.info(f"User '{user_id}' deleted successfully by {current_user.get('user_id')}")
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": f"User '{user_id}' deleted successfully"
                }
            )
        else:
            logger.error(f"Failed to delete user '{user_id}'")
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to delete user. Please try again."}
            )
            
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )
    
# ============================================
# GET AVAILABLE PROPERTIES (For Dashboard)
# ============================================
@router.get("/get_available")
async def get_available_properties(request: Request):
    """Get all available properties for dashboard display"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        all_properties = db.get_collection("properties")
        available_properties = [p for p in all_properties if p.get("available", True)]
        
        # Sort by created_at (newest first)
        available_properties.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return JSONResponse({
            "success": True,
            "properties": available_properties,
            "count": len(available_properties)
        })
        
    except Exception as e:
        logger.error(f"Error getting available properties: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET PROPERTY DETAILS (With agent info)
# ============================================
@router.get("/get_property_details/{property_id}")
async def get_property_details(request: Request, property_id: str):
    """Get detailed information about a property including agent info"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        properties = db.get_collection("properties")
        property_item = None
        for p in properties:
            if p.get("_id") == property_id or p.get("id") == property_id:
                property_item = p
                break
        
        if not property_item:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Property not found"}
            )
        
        # Get agent info (creator of the property)
        agent_info = {
            "name": "Property Manager",
            "phone": "Not provided",
            "email": "Not provided"
        }
        
        created_by = property_item.get("created_by")
        if created_by:
            users = db.get_collection("users")
            for u in users:
                if u.get("user_id") == created_by:
                    agent_info = {
                        "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("user_id"),
                        "phone": u.get("phone", "Not provided"),
                        "email": u.get("email", "Not provided")
                    }
                    break
        
        return JSONResponse({
            "success": True,
            "property": property_item,
            "agent_name": agent_info["name"],
            "agent_phone": agent_info["phone"],
            "agent_email": agent_info["email"]
        })
        
    except Exception as e:
        logger.error(f"Error getting property details: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )



# ============================================
# REQUEST PROPERTY (Interest)
# ============================================
@router.post("/request_property")
async def request_property(request: Request):
    """User expresses interest in a property"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        body = await request.json()
        property_id = body.get("property_id")
        
        if not property_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Property ID is required"}
            )
        
        # Find property
        properties = db.get_collection("properties")
        property_item = None
        for p in properties:
            if p.get("_id") == property_id or p.get("id") == property_id:
                property_item = p
                break
        
        if not property_item:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Property not found"}
            )
        
        # Get agent
        created_by = property_item.get("created_by")
        agent_user = None
        users = db.get_collection("users")
        for u in users:
            if u.get("user_id") == created_by:
                agent_user = u
                break
        
        # Notify agent
        if agent_user:
            create_notification(
                agent_user.get("user_id"),
                "property_request",
                f"🏠 {current_user.get('user_id')} has requested information about your property '{property_item.get('name')}'.",
                {
                    "property_id": property_id,
                    "property_name": property_item.get("name"),
                    "requester": current_user.get("user_id")
                }
            )
            
            # Send email to agent
            email_body = f"""
Hello {agent_user.get('first_name', 'Agent')},

{current_user.get('user_id')} has requested information about your property '{property_item.get('name')}'.

Please login to view the details and respond.

Regards,
Xtopus Team
"""
            template_params = {
                'seller_email': agent_user.get("email"),
                'to_name': agent_user.get('first_name', 'Agent'),
                'name': f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
                'email': current_user.get("email", ""),
                'message': email_body,
                'subject': f"Xtopus - Property Request: {property_item.get('name')}",
                'product_name': property_item.get('name')  # ← ADD THIS
            }
            
            send_emailjs_notification(
                agent_user.get("email"),
                f"Xtopus - Property Request: {property_item.get('name')}",
                email_body,
                template_params
            )

        
        return JSONResponse({
            "success": True,
            "message": f"Your request for '{property_item.get('name')}' has been sent to the agent."
        })
        
    except Exception as e:
        logger.error(f"Error requesting property: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )    
    
# ============================================
# GET USERS LIST (With Tenant Status)
# ============================================
@router.get("/get_users")
async def get_users_list(request: Request):
    """Get list of all users with full details for management"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        users = db.get_collection("users")
        
        # Return users with full details
        user_list = []
        for u in users:
            # Determine tenant status display
            tenant_status = u.get("tenant_status")
            tenant_status_display = "N/A"
            
            if u.get("user_category") == "Tenant":
                if tenant_status == "active":
                    tenant_status_display = "✅ Active Tenant"
                elif tenant_status == "pending_payment":
                    tenant_status_display = "⏳ Payment Pending"
                elif tenant_status == "pending":
                    tenant_status_display = "⏳ Pending Approval"
                else:
                    tenant_status_display = "Tenant"
            elif tenant_status == "pending" and u.get("user_category") != "Tenant":
                tenant_status_display = "⏳ Request Pending"
            
            user_list.append({
                "user_id": u.get("user_id", ""),
                "username": u.get("username", ""),
                "first_name": u.get("first_name", ""),
                "last_name": u.get("last_name", ""),
                "email": u.get("email", ""),
                "user_category": u.get("user_category", "User"),
                "activity_status": u.get("activity_status", "Active"),
                "payment_status": u.get("payment_status", "free"),
                "tenant_status": tenant_status,
                "tenant_status_display": tenant_status_display,
                "assigned_property": u.get("assigned_property_name", ""),
                "rental_start_date": u.get("rental_start_date", ""),
                "rental_end_date": u.get("rental_end_date", ""),
                "created_at": u.get("created_at"),
                "last_login": u.get("last_login"),
                "created_by": u.get("created_by", "")
            })
        
        return JSONResponse({
            "success": True,
            "users": user_list,
            "count": len(user_list)
        })
        
    except Exception as e:
        logger.error(f"Error getting users list: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET USER DETAILS (For management)
# ============================================
@router.get("/get_user_details/{user_id}")
async def get_user_details(request: Request, user_id: str):
    """Get detailed information about a specific user"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        users = db.get_collection("users")
        target_user = None
        for u in users:
            if u.get("user_id") == user_id:
                target_user = u
                break
        
        if not target_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "User not found"}
            )
        
        return JSONResponse({
            "success": True,
            "user": target_user
        })
        
    except Exception as e:
        logger.error(f"Error getting user details: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET AVAILABLE PROPERTIES
# ============================================
@router.get("/get_available_properties")
async def get_available_properties(request: Request):
    """Get all available properties for dropdown"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        all_properties = db.get_collection("properties")
        available_properties = []
        
        for prop in all_properties:
            if prop.get("available", True):
                available_properties.append({
                    "_id": prop.get("_id"),
                    "id": prop.get("id"),
                    "name": prop.get("name"),
                    "price": prop.get("price"),
                    "building_name": prop.get("building_name", "Unknown Building")
                })
        
        return JSONResponse({
            "success": True,
            "properties": available_properties
        })
        
    except Exception as e:
        logger.error(f"Error getting available properties: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET ALL USERS (For dropdown - keeping original)
# ============================================
@router.get("/get_all_users_for_dropdown")
async def get_all_users_for_dropdown(request: Request):
    """Get all users for dropdown selection (with names)"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        all_users = db.get_collection("users")
        user_list = []
        
        for user in all_users:
            # Skip current user
            if user.get("user_id") == current_user.get("user_id"):
                continue
            
            user_list.append({
                "user_id": user.get("user_id"),
                "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                "email": user.get("email"),
                "category": user.get("user_category", "User")
            })
        
        # Sort by user_id
        user_list.sort(key=lambda x: x["user_id"])
        
        return JSONResponse({
            "success": True,
            "users": user_list
        })
        
    except Exception as e:
        logger.error(f"Error getting all users for dropdown: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET BUILDINGS
# ============================================
@router.get("/get_buildings")
async def get_buildings(request: Request):
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        buildings = db.get_collection("buildings")
        return JSONResponse({"buildings": buildings})
        
    except Exception as e:
        logger.error(f"Error getting buildings: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET PROPERTIES
# ============================================
@router.get("/get_properties")
async def get_properties(request: Request):
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        properties = db.get_collection("properties")
        return JSONResponse({"properties": properties})
        
    except Exception as e:
        logger.error(f"Error getting properties: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# MANAGE USER STATUS
# ============================================
@router.post("/manage_user_status")
async def manage_user_status(request: Request):
    """Activate or deactivate a user"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        data = await request.json()
        user_id = data.get("user_id")
        action = data.get("action")
        
        if not user_id or action not in ["activate", "deactivate"]:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Invalid request. Need user_id and action (activate/deactivate)"}
            )
        
        users = db.get_collection("users")
        target_user = None
        
        for user in users:
            if user.get("user_id") == user_id:
                target_user = user
                break
        
        if not target_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": f"User '{user_id}' not found"}
            )
        
        # Prevent modifying Super Administrator
        if target_user.get("user_category") == "Super Administrator":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Cannot modify Super Administrator"}
            )
        
        # If current user is Administrator (not Super Admin), check if they created this user
        if category == "Administrator":
            created_by = target_user.get("created_by")
            if created_by != current_user.get("user_id"):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "You can only manage users you created"}
                )
        
        new_status = "Active" if action == "activate" else "Inactive"
        target_user["activity_status"] = new_status
        target_user["updated_at"] = datetime.now().isoformat()
        
        success = db.update_collection_item("users", target_user.get("_id"), target_user)
        
        if success:
            return JSONResponse({
                "success": True,
                "message": f"User '{user_id}' {action}d successfully"
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to update user"}
            )
            
    except Exception as e:
        logger.error(f"Error managing user status: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# CREATE BUILDING (Fixed)
# ============================================
@router.post("/create_building")
async def create_building(
    request: Request,
    name: str = Form(None),
    description: str = Form(None),
    address: str = Form(None),
    state: str = Form(None),
    unit_type: str = Form(None),
    number_of_units: int = Form(None),
    category: str = Form(None),
    photos: List[UploadFile] = File(None)
):
    try:
        # Get current user from session
        session_token = request.cookies.get("session_token")
        if not session_token:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        current_user_data = security.get_current_user(session_token)
        if not current_user_data:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Invalid session"}
            )
        
        # Get full user from database
        users = db.get_collection("users")
        current_user = None
        for u in users:
            if u.get("user_id") == current_user_data.get("user_id"):
                current_user = u
                break
        
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "User not found"}
            )
        
        # Check if user has permission
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only Administrators can create buildings"}
            )
        
        # Validate required fields
        if not all([name, description, address, state, unit_type, number_of_units, category]):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "All fields are required"}
            )
       
        
        # After getting current_user, add this usage check:
        user_id = current_user.get("user_id")
        payment_status = current_user.get("payment_status", "free")
        
        # Count existing buildings created by this user
        buildings = db.get_collection("buildings")
        existing_buildings = [b for b in buildings if b.get("created_by") == user_id]
        
        # Check if free user has reached limit
        if payment_status == "free" and len(existing_buildings) >= 1:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False, 
                    "detail": "Free plan users can only create 1 building. Please upgrade your plan to create more."
                }
            )
        #End of the usage check
        
        
        # Upload photos
        photo_urls = []
        if photos:
            validate_photos(photos)
            for photo in photos:
                try:
                    url = upload_to_firebase(photo, f"buildings/{datetime.now().strftime('%Y%m')}")
                    photo_urls.append(url)
                except Exception as e:
                    logger.error(f"Failed to upload photo: {e}")
       
        
       
        # Create building
        building = {
            "_id": f"building_{int(datetime.now().timestamp())}",
            "id": f"building_{int(datetime.now().timestamp())}",
            "name": name,
            "description": description,
            "address": address,
            "state": state,
            "unit_type": unit_type,
            "number_of_units": int(number_of_units),
            "category": category,
            "created_by": current_user.get("user_id"),
            "created_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            "photos": photo_urls,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        success = db.add_to_collection("buildings", building)
        
        if success:
            return JSONResponse({
                "success": True,
                "message": f"Building '{name}' created successfully with {len(photo_urls)} photos",
                "building": building
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to create building"}
            )
            
    except Exception as e:
        logger.error(f"Error creating building: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET ADMIN DASHBOARD STATS
# ============================================
@router.get("/get_admin_dashboard_stats")
async def get_admin_dashboard_stats(request: Request):
    """Get dashboard statistics for admin"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        users = db.get_collection("users")
        complaints = db.get_collection("complaints")
        
        # Count pending tenants (users with tenant_status='pending')
        pending_tenants = [u for u in users if u.get("tenant_status") == "pending" and u.get("user_category") != "Tenant"]
        
        # Count pending payments (users with tenant_status='pending_payment')
        pending_payments = [u for u in users if u.get("tenant_status") == "pending_payment" and u.get("user_category") == "Tenant"]
        
        # Count new messages (unread chats)
        chats = db.get_collection("chats")
        new_messages = 0
        for chat in chats:
            if not chat.get("read", False):
                new_messages += 1
        
        return JSONResponse({
            "success": True,
            "stats": {
                "pending_tenants": len(pending_tenants),
                "pending_payments": len(pending_payments),
                "new_messages": new_messages
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting admin dashboard stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )
    
    
# ============================================
# CREATE PROPERTY (Fixed)
# ============================================
@router.post("/create_property")
async def create_property(
    request: Request,
    name: str = Form(None),
    description: str = Form(None),
    building_id: str = Form(None),
    price: float = Form(None),
    visibility: str = Form("local"),
    photos: List[UploadFile] = File(None)
):
    try:
        # Get current user from session
        session_token = request.cookies.get("session_token")
        if not session_token:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        current_user_data = security.get_current_user(session_token)
        if not current_user_data:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Invalid session"}
            )
        
        # Get full user from database
        users = db.get_collection("users")
        current_user = None
        for u in users:
            if u.get("user_id") == current_user_data.get("user_id"):
                current_user = u
                break
        
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "User not found"}
            )
        
        # Check if user has permission
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only Administrators can create properties"}
            )
        
        # Validate required fields
        if not all([name, description, building_id, price]):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "All fields are required"}
            )
        
        
        # After getting current_user, add this usage check:
        user_id = current_user.get("user_id")
        payment_status = current_user.get("payment_status", "free")
        
        # Count existing properties created by this user
        properties = db.get_collection("properties")
        existing_properties = [p for p in properties if p.get("created_by") == user_id]
        
        # Check if free user has reached limit
        if payment_status == "free" and len(existing_properties) >= 1:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False, 
                    "detail": "Free plan users can only create 1 property. Please upgrade your plan to create more."
                }
            )
        
        
        # Find the building
        buildings = db.get_collection("buildings")
        building = None
        for b in buildings:
            if b.get("_id") == building_id or b.get("id") == building_id:
                building = b
                break
        
        if not building:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Building not found"}
            )
        
        # Upload photos
        photo_urls = []
        if photos:
            validate_photos(photos)
            for photo in photos:
                try:
                    url = upload_to_firebase(photo, f"properties/{datetime.now().strftime('%Y%m')}")
                    photo_urls.append(url)
                except Exception as e:
                    logger.error(f"Failed to upload photo: {e}")
        
        # Create property
        property_data = {
            "_id": f"property_{int(datetime.now().timestamp())}",
            "id": f"property_{int(datetime.now().timestamp())}",
            "name": name,
            "description": description,
            "building_id": building_id,
            "building_name": building.get("name"),
            "building_address": building.get("address"),
            "building_state": building.get("state"),
            "price": float(price),
            "visibility": visibility,
            "photos": photo_urls,
            "available": True,
            "created_by": current_user.get("user_id"),
            "created_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        success = db.add_to_collection("properties", property_data)
        
        if success:
            return JSONResponse({
                "success": True,
                "message": f"Property '{name}' created successfully with {len(photo_urls)} photos",
                "property": property_data
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to create property"}
            )
            
    except Exception as e:
        logger.error(f"Error creating property: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# Add this to admin.py after the existing create_property function

# ============================================
# CREATE MULTIPLE PROPERTIES (Batch Creation)
# ============================================
@router.post("/create_multiple_properties")
async def create_multiple_properties(
    request: Request,
    name: str = Form(None),
    description: str = Form(None),
    building_id: str = Form(None),
    price: float = Form(None),
    visibility: str = Form("local"),
    count: int = Form(1),
    photos: List[UploadFile] = File(None)
):
    """Create multiple properties with sequential numbering"""
    try:
        # Get current user from session
        session_token = request.cookies.get("session_token")
        if not session_token:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        current_user_data = security.get_current_user(session_token)
        if not current_user_data:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Invalid session"}
            )
        
        # Get full user from database
        users = db.get_collection("users")
        current_user = None
        for u in users:
            if u.get("user_id") == current_user_data.get("user_id"):
                current_user = u
                break
        
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "User not found"}
            )
        
        # Check if user has permission
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only Administrators can create properties"}
            )
        
        # Validate required fields
        if not all([name, description, building_id, price]):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "All fields are required"}
            )
        
        if count < 1 or count > 20:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Number of properties must be between 1 and 20"}
            )
        
        # Find the building
        buildings = db.get_collection("buildings")
        building = None
        for b in buildings:
            if b.get("_id") == building_id or b.get("id") == building_id:
                building = b
                break
        
        if not building:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Building not found"}
            )
        
        # Upload photos once (reuse for all properties)
        photo_urls = []
        if photos:
            validate_photos(photos)
            for photo in photos:
                try:
                    url = upload_to_firebase(photo, f"properties/{datetime.now().strftime('%Y%m')}")
                    photo_urls.append(url)
                except Exception as e:
                    logger.error(f"Failed to upload photo: {e}")
        
        # Check usage limits
        user_id = current_user.get("user_id")
        payment_status = current_user.get("payment_status", "free")
        
        # Count existing properties created by this user
        all_properties = db.get_collection("properties")
        existing_properties = [p for p in all_properties if p.get("created_by") == user_id]
        
        # Check if free user has reached limit
        if payment_status == "free" and len(existing_properties) + count > 1:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False, 
                    "detail": f"Free plan users can only create 1 property total. You already have {len(existing_properties)}. Please upgrade your plan or reduce the number of properties."
                }
            )
        
        # Check if there are existing properties with similar names to determine starting number
        existing_similar = [p for p in all_properties if p.get("name", "").startswith(name)]
        base_name = name
        created_properties = []
        
        for i in range(count):
            # Generate property name with number
            if count > 1:
                property_name = f"{base_name} - Unit {i + 1}"
            else:
                property_name = base_name
            
            # Create property
            property_data = {
                "_id": f"property_{int(datetime.now().timestamp())}_{i}",
                "id": f"property_{int(datetime.now().timestamp())}_{i}",
                "name": property_name,
                "description": description,
                "building_id": building_id,
                "building_name": building.get("name"),
                "building_address": building.get("address"),
                "building_state": building.get("state"),
                "price": float(price),
                "visibility": visibility,
                "photos": photo_urls,
                "available": True,
                "created_by": current_user.get("user_id"),
                "created_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "unit_number": i + 1,
                "parent_name": base_name if count > 1 else None
            }
            
            success = db.add_to_collection("properties", property_data)
            if success:
                created_properties.append(property_data)
        
        if created_properties:
            return JSONResponse({
                "success": True,
                "message": f"Created {len(created_properties)} properties successfully with {len(photo_urls)} photos each",
                "properties": created_properties,
                "count": len(created_properties)
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to create properties"}
            )
            
    except Exception as e:
        logger.error(f"Error creating multiple properties: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )
    
# ============================================
# GET NOTIFICATION COUNTS FOR HEADER BADGE (Role-Based)
# ============================================
@router.get("/get_notification_counts")
async def get_notification_counts(request: Request):
    """Get notification counts for the header badge based on user role"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        user_id = current_user.get("user_id")
        user_category = current_user.get("user_category", "")
        
        # Get all users and data
        users = db.get_collection("users")
        properties = db.get_collection("properties")
        chat_data = db.get_data()
        
        # Initialize counts
        pending_tenants = 0
        pending_payments = 0
        unread_messages = 0
        
        # ============================================
        # ROLE-BASED NOTIFICATION COUNTS
        # ============================================
        
        if user_category in ["Super Administrator", "Administrator"]:
            # ADMIN: See all pending tenants and payments
            pending_tenant_ids = set()
            for u in users:
                if u.get("tenant_status") == "pending" and u.get("user_category") != "Tenant":
                    pending_tenant_ids.add(u.get("user_id"))
            pending_tenants = len(pending_tenant_ids)
            
            pending_payment_ids = set()
            for u in users:
                if u.get("user_category") == "Tenant" and u.get("tenant_status") == "pending_payment":
                    pending_payment_ids.add(u.get("user_id"))
            pending_payments = len(pending_payment_ids)
            
        elif user_category == "Sub-Administrator":
            # SUB-ADMIN: See pending tenants they created, and pending payments for their tenants
            # Get all users created by this sub-admin (agents and regular users)
            created_users = []
            for u in users:
                if u.get("created_by") == user_id:
                    created_users.append(u.get("user_id"))
            
            # Pending tenants created by this sub-admin
            pending_tenant_ids = set()
            for u in users:
                if (u.get("tenant_status") == "pending" and 
                    u.get("user_category") != "Tenant" and 
                    u.get("created_by") == user_id):
                    pending_tenant_ids.add(u.get("user_id"))
            pending_tenants = len(pending_tenant_ids)
            
            # Pending payments for tenants assigned by this sub-admin or their agents
            pending_payment_ids = set()
            for u in users:
                if (u.get("user_category") == "Tenant" and 
                    u.get("tenant_status") == "pending_payment"):
                    # Check if assigned by this sub-admin or by an agent they created
                    assigned_by = u.get("tenant_assigned_by")
                    if assigned_by == user_id or assigned_by in created_users:
                        pending_payment_ids.add(u.get("user_id"))
            pending_payments = len(pending_payment_ids)
            
        elif user_category == "Agent":
            # AGENT: See pending payments for their tenants, and their own messages
            # Pending payments for tenants assigned by this agent
            pending_payment_ids = set()
            for u in users:
                if (u.get("user_category") == "Tenant" and 
                    u.get("tenant_status") == "pending_payment" and
                    u.get("tenant_assigned_by") == user_id):
                    pending_payment_ids.add(u.get("user_id"))
            pending_payments = len(pending_payment_ids)
        
        # ============================================
        # UNREAD MESSAGES (All Users)
        # ============================================
        chat_messages = chat_data.get("chat_messages", [])
        for msg in chat_messages:
            if msg.get("receiver_id") == user_id and not msg.get("read", False):
                unread_messages += 1
        
        # ============================================
        # TOTAL NOTIFICATIONS
        # ============================================
        total_notifications = pending_tenants + pending_payments + unread_messages
        
        return JSONResponse({
            "success": True,
            "counts": {
                "pending_tenants": pending_tenants,
                "pending_payments": pending_payments,
                "unread_messages": unread_messages,
                "total": total_notifications,
                "user_role": user_category  # For debugging
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting notification counts: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )    
# ============================================
# MARK ALL NOTIFICATIONS AS READ (Role-Based)
# ============================================
@router.post("/mark_notifications_read")
async def mark_notifications_read(request: Request):
    """Mark all notifications as read for the current user"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        user_id = current_user.get("user_id")
        data = db.get_data()
        
        # Mark notifications as read
        notifications = data.get("notifications", [])
        updated = False
        for notif in notifications:
            if notif.get("user_id") == user_id and not notif.get("read", False):
                notif["read"] = True
                updated = True
        
        # Also mark chat messages as read for this user
        chat_messages = data.get("chat_messages", [])
        for msg in chat_messages:
            if msg.get("receiver_id") == user_id and not msg.get("read", False):
                msg["read"] = True
                updated = True
        
        if updated:
            db.update_data(data)
        
        return JSONResponse({
            "success": True,
            "message": "All notifications marked as read"
        })
        
    except Exception as e:
        logger.error(f"Error marking notifications as read: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )
    
# Add these new endpoints to admin.py after the existing ones

# ============================================
# GET USER PAYMENT STATUS AND USAGE COUNTS
# ============================================
@router.get("/get_user_usage_counts")
async def get_user_usage_counts(request: Request):
    """Get the usage counts for the current user (buildings, properties, tenants created)"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        user_id = current_user.get("user_id")
        payment_status = current_user.get("payment_status", "free")
        
        # Count buildings created by this user
        buildings = db.get_collection("buildings")
        buildings_count = len([b for b in buildings if b.get("created_by") == user_id])
        
        # Count properties created by this user
        properties = db.get_collection("properties")
        properties_count = len([p for p in properties if p.get("created_by") == user_id])
        
        # Count tenants assigned by this user (users with tenant_status and assigned_by this user)
        users = db.get_collection("users")
        tenants_count = len([u for u in users if u.get("tenant_assigned_by") == user_id and u.get("user_category") == "Tenant"])
        
        return JSONResponse({
            "success": True,
            "payment_status": payment_status,
            "usage": {
                "buildings": buildings_count,
                "properties": properties_count,
                "tenants": tenants_count,
                "max_buildings": 1 if payment_status == "free" else 999,
                "max_properties": 1 if payment_status == "free" else 999,
                "max_tenants": 1 if payment_status == "free" else 999,
                "is_free": payment_status == "free"
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting user usage counts: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# REQUEST ROLE UPGRADE (Regular User)
# ============================================
@router.post("/request_role_upgrade")
async def request_role_upgrade(request: Request):
    """Regular user requests to be upgraded to a higher role"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        body = await request.json()
        requested_role = body.get("requested_role")
        reason = body.get("reason", "")
        
        if not requested_role:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Requested role is required"}
            )
        
        # Only regular users can request upgrades
        user_category = current_user.get("user_category", "User")
        if user_category != "User":
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Only regular users can request role upgrades"}
            )
        
        # Valid roles to upgrade to
        valid_roles = ["Administrator", "Sub-Administrator", "Agent", "Tenant"]
        if requested_role not in valid_roles:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": f"Invalid role. Must be one of: {', '.join(valid_roles)}"}
            )
        
        # Check if there's already a pending request
        users = db.get_collection("users")
        target_user = None
        for u in users:
            if u.get("user_id") == current_user.get("user_id"):
                target_user = u
                break
        
        if target_user.get("role_upgrade_request"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "You already have a pending role upgrade request"}
            )
        
        # Create the request
        target_user["role_upgrade_request"] = {
            "requested_role": requested_role,
            "reason": reason,
            "status": "pending",
            "requested_at": datetime.now().isoformat(),
            "request_id": f"upgrade_{int(datetime.now().timestamp())}"
        }
        
        success = db.update_collection_item("users", target_user.get("_id"), target_user)
        
        if success:
            # Notify all administrators
            admins = [u for u in users if u.get("user_category") in ["Super Administrator", "Administrator"]]
            for admin in admins:
                create_notification(
                    admin.get("user_id"),
                    "role_upgrade_request",
                    f"📋 {current_user.get('user_id')} has requested to be upgraded to {requested_role}. Reason: {reason}",
                    {
                        "user_id": current_user.get("user_id"),
                        "requested_role": requested_role,
                        "reason": reason,
                        "request_id": target_user["role_upgrade_request"]["request_id"]
                    }
                )
                
                # Send email to admins
                email_body = f"""
Hello {admin.get('first_name', 'Admin')},

A user has requested a role upgrade.

User: {current_user.get('user_id')} ({current_user.get('first_name')} {current_user.get('last_name')})
Requested Role: {requested_role}
Reason: {reason}

Please login to review and approve or reject this request.

Regards,
Xtopus Team
"""
                template_params = {
                    'seller_email': admin.get("email"),
                    'to_name': admin.get('first_name', 'Admin'),
                    'name': 'Xtopus Property Management',
                    'email': 'geocorpsys@gmail.com',
                    'message': email_body,
                    'subject': "Xtopus - Role Upgrade Request",
                    'product_name': "Role Upgrade"
                }
                send_emailjs_notification(
                    admin.get("email"),
                    "Xtopus - Role Upgrade Request",
                    email_body,
                    template_params
                )
            
            # Notify the user
            create_notification(
                current_user.get("user_id"),
                "role_upgrade_submitted",
                f"Your request to become a {requested_role} has been submitted. Awaiting administrator approval."
            )
            
            return JSONResponse({
                "success": True,
                "message": f"Your request to become a {requested_role} has been submitted. Awaiting administrator approval.",
                "request_id": target_user["role_upgrade_request"]["request_id"]
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to submit request"}
            )
            
    except Exception as e:
        logger.error(f"Error requesting role upgrade: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET ROLE UPGRADE REQUESTS (Admin)
# ============================================
@router.get("/get_role_upgrade_requests")
async def get_role_upgrade_requests(request: Request):
    """Administrators get all pending role upgrade requests"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        users = db.get_collection("users")
        requests = []
        
        for u in users:
            upgrade_req = u.get("role_upgrade_request")
            if upgrade_req and upgrade_req.get("status") == "pending":
                requests.append({
                    "user_id": u.get("user_id"),
                    "first_name": u.get("first_name"),
                    "last_name": u.get("last_name"),
                    "email": u.get("email"),
                    "requested_role": upgrade_req.get("requested_role"),
                    "reason": upgrade_req.get("reason", ""),
                    "requested_at": upgrade_req.get("requested_at"),
                    "request_id": upgrade_req.get("request_id")
                })
        
        return JSONResponse({
            "success": True,
            "requests": requests,
            "count": len(requests)
        })
        
    except Exception as e:
        logger.error(f"Error getting role upgrade requests: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# APPROVE/REJECT ROLE UPGRADE (Admin)
# ============================================
@router.post("/process_role_upgrade")
async def process_role_upgrade(request: Request):
    """Administrator approves or rejects a role upgrade request"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        body = await request.json()
        user_id = body.get("user_id")
        action = body.get("action")  # "approve" or "reject"
        requested_role = body.get("requested_role")
        
        if not user_id or not action:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "User ID and action are required"}
            )
        
        users = db.get_collection("users")
        target_user = None
        target_index = -1
        
        for idx, u in enumerate(users):
            if u.get("user_id") == user_id:
                target_user = u
                target_index = idx
                break
        
        if not target_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "User not found"}
            )
        
        upgrade_req = target_user.get("role_upgrade_request")
        if not upgrade_req or upgrade_req.get("status") != "pending":
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "No pending upgrade request found for this user"}
            )
        
        if action == "approve":
            new_role = upgrade_req.get("requested_role")
            if not new_role:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "detail": "No requested role found"}
                )
            
            # Update the user's role
            target_user["user_category"] = new_role
            target_user["role_upgrade_request"]["status"] = "approved"
            target_user["role_upgrade_request"]["processed_by"] = current_user.get("user_id")
            target_user["role_upgrade_request"]["processed_at"] = datetime.now().isoformat()
            target_user["upgraded_by"] = current_user.get("user_id")
            target_user["upgraded_at"] = datetime.now().isoformat()
            
            # If upgrading to Tenant, set appropriate fields
            if new_role == "Tenant":
                target_user["tenant_status"] = "active"
                target_user["activity_status"] = "Active"
            
            message = f"User {user_id} has been upgraded to {new_role} by {current_user.get('user_id')}"
            
            # Notify the user
            create_notification(
                user_id,
                "role_upgrade_approved",
                f"🎉 Your request to become a {new_role} has been APPROVED by {current_user.get('user_id')}!"
            )
            
            # Send email to the user
            email_body = f"""
Hello {target_user.get('first_name', 'User')},

🎉 Congratulations! Your request to become a {new_role} has been APPROVED.

You can now login and access your new role features.

Regards,
Xtopus Team
"""
            template_params = {
                'seller_email': target_user.get("email"),
                'to_name': target_user.get('first_name', 'User'),
                'name': 'Xtopus Property Management',
                'email': 'geocorpsys@gmail.com',
                'message': email_body,
                'subject': f"Xtopus - Role Upgrade Approved: {new_role}",
                'product_name': "Role Upgrade"
            }
            send_emailjs_notification(
                target_user.get("email"),
                f"Xtopus - Role Upgrade Approved: {new_role}",
                email_body,
                template_params
            )
            
        elif action == "reject":
            target_user["role_upgrade_request"]["status"] = "rejected"
            target_user["role_upgrade_request"]["processed_by"] = current_user.get("user_id")
            target_user["role_upgrade_request"]["processed_at"] = datetime.now().isoformat()
            target_user["role_upgrade_request"]["rejection_reason"] = body.get("reason", "No reason provided")
            
            message = f"User {user_id}'s role upgrade request has been rejected by {current_user.get('user_id')}"
            
            # Notify the user
            create_notification(
                user_id,
                "role_upgrade_rejected",
                f"❌ Your request to become a {upgrade_req.get('requested_role')} has been REJECTED by {current_user.get('user_id')}."
            )
            
            # Send email to the user
            email_body = f"""
Hello {target_user.get('first_name', 'User')},

Your request to become a {upgrade_req.get('requested_role')} has been REJECTED.

Reason: {body.get('reason', 'No reason provided')}

If you have any questions, please contact support.

Regards,
Xtopus Team
"""
            template_params = {
                'seller_email': target_user.get("email"),
                'to_name': target_user.get('first_name', 'User'),
                'name': 'Xtopus Property Management',
                'email': 'geocorpsys@gmail.com',
                'message': email_body,
                'subject': "Xtopus - Role Upgrade Rejected",
                'product_name': "Role Upgrade"
            }
            send_emailjs_notification(
                target_user.get("email"),
                "Xtopus - Role Upgrade Rejected",
                email_body,
                template_params
            )
        else:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Invalid action. Use 'approve' or 'reject'"}
            )
        
        # Update the user in the database
        data = db.get_data()
        data["users"][target_index] = target_user
        success = db.update_data(data)
        
        if success:
            return JSONResponse({
                "success": True,
                "message": message,
                "user_id": user_id,
                "new_role": target_user.get("user_category") if action == "approve" else upgrade_req.get("requested_role")
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to process request"}
            )
            
    except Exception as e:
        logger.error(f"Error processing role upgrade: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET USER PAYMENT STATUS (For dashboard display)
# ============================================
@router.get("/get_user_payment_status")
async def get_user_payment_status(request: Request):
    """Get the current user's payment status and plan information"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        payment_status = current_user.get("payment_status", "free")
        
        # Count usage
        user_id = current_user.get("user_id")
        buildings = db.get_collection("buildings")
        buildings_count = len([b for b in buildings if b.get("created_by") == user_id])
        
        properties = db.get_collection("properties")
        properties_count = len([p for p in properties if p.get("created_by") == user_id])
        
        users = db.get_collection("users")
        tenants_count = len([u for u in users if u.get("tenant_assigned_by") == user_id and u.get("user_category") == "Tenant"])
        
        # Determine if user is on free plan and has reached limits
        is_free = payment_status == "free"
        can_create_building = not (is_free and buildings_count >= 1)
        can_create_property = not (is_free and properties_count >= 1)
        can_assign_tenant = not (is_free and tenants_count >= 1)
        
        return JSONResponse({
            "success": True,
            "payment_status": payment_status,
            "usage": {
                "buildings": buildings_count,
                "properties": properties_count,
                "tenants": tenants_count,
                "max_buildings": 1 if is_free else 999,
                "max_properties": 1 if is_free else 999,
                "max_tenants": 1 if is_free else 999
            },
            "permissions": {
                "can_create_building": can_create_building,
                "can_create_property": can_create_property,
                "can_assign_tenant": can_assign_tenant
            },
            "is_free": is_free,
            "message": "You are on the Free Plan. You can create 1 building, 1 property, and assign 1 tenant." if is_free else "You are on a Paid Plan with unlimited access."
        })
        
    except Exception as e:
        logger.error(f"Error getting user payment status: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )    


# Add or update the upgrade_user_plan endpoint to use Paystack reference:

@router.post("/upgrade_user_plan")
async def upgrade_user_plan(request: Request):
    """Upgrade a user from free to paid plan (called after Paystack verification)"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        body = await request.json()
        payment_reference = body.get("payment_reference")
        amount = body.get("amount")
        plan_type = body.get("plan_type", "monthly")
        
        if not payment_reference:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Payment reference is required"}
            )
        
        # Verify payment with Paystack
        import requests
        PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', 'sk_test_xxx')
        
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        
        verify_response = requests.get(
            f"https://api.paystack.co/transaction/verify/{payment_reference}",
            headers=headers,
            timeout=30
        )
        
        if verify_response.status_code != 200:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to verify payment with Paystack"}
            )
        
        verify_data = verify_response.json()
        if not verify_data.get("status"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Payment verification failed"}
            )
        
        # Update user's payment status
        users = db.get_collection("users")
        target_user = None
        for u in users:
            if u.get("user_id") == current_user.get("user_id"):
                target_user = u
                break
        
        if not target_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "User not found"}
            )
        
        target_user["payment_status"] = "paid"
        target_user["plan_type"] = plan_type
        target_user["upgraded_at"] = datetime.now().isoformat()
        target_user["payment_reference"] = payment_reference
        target_user["upgrade_amount"] = amount or (15000 if plan_type == "monthly" else 162000)
        
        # Set expiry
        from datetime import timedelta
        if plan_type == "monthly":
            target_user["plan_expiry"] = (datetime.now() + timedelta(days=30)).isoformat()
        else:
            target_user["plan_expiry"] = (datetime.now() + timedelta(days=365)).isoformat()
        
        success = db.update_collection_item("users", target_user.get("_id"), target_user)
        
        if success:
            create_notification(
                current_user.get("user_id"),
                "plan_upgraded",
                f"🎉 Your plan has been upgraded to PAID ({plan_type})! You now have unlimited access."
            )
            
            return JSONResponse({
                "success": True,
                "message": "Plan upgraded successfully! You now have unlimited access."
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to upgrade plan"}
            )
            
    except Exception as e:
        logger.error(f"Error upgrading plan: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )    

# Add these endpoints to admin.py

# ============================================
# BACKUP DATABASE (Super Admin only)
# ============================================
@router.get("/backup_database")
async def backup_database(request: Request):
    """Backup the entire database - Super Admin only"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Only Super Admin can backup
        if current_user.get("user_category") != "Super Administrator":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied. Only Super Administrators can backup the database."}
            )
        
        # Get all data
        data = db.get_data()
        
        # Add backup metadata
        backup_data = {
            "backup_info": {
                "created_at": datetime.now().isoformat(),
                "created_by": current_user.get("user_id"),
                "version": "1.0.0",
                "total_users": len(data.get("users", [])),
                "total_buildings": len(data.get("buildings", [])),
                "total_properties": len(data.get("properties", [])),
                "total_payments": len(data.get("payments", []))
            },
            "data": data
        }
        
        return JSONResponse({
            "success": True,
            "message": "Database backup created successfully",
            "data": backup_data
        })
        
    except Exception as e:
        logger.error(f"Error backing up database: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# RESTORE DATABASE (Super Admin only)
# ============================================
@router.post("/restore_database")
async def restore_database(request: Request):
    """Restore the entire database from backup - Super Admin only"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Only Super Admin can restore
        if current_user.get("user_category") != "Super Administrator":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied. Only Super Administrators can restore the database."}
            )
        
        body = await request.json()
        
        # Validate backup data structure
        if "data" not in body or "backup_info" not in body:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Invalid backup file format"}
            )
        
        backup_data = body.get("data", {})
        
        # Validate that backup contains required collections
        required_collections = ["users", "buildings", "properties"]
        for collection in required_collections:
            if collection not in backup_data:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "detail": f"Missing required collection: {collection}"}
                )
        
        # Restore the data
        success = db.update_data(backup_data)
        
        if success:
            # Log the restore
            logger.info(f"Database restored by {current_user.get('user_id')} at {datetime.now().isoformat()}")
            
            return JSONResponse({
                "success": True,
                "message": "Database restored successfully"
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to restore database"}
            )
        
    except Exception as e:
        logger.error(f"Error restoring database: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )    
    
# ============================================
# UPDATE BUILDING - SIMPLE FIX
# ============================================
@router.put("/update_building/{building_id}")
async def update_building(
    request: Request,
    building_id: str,
    name: str = Form(None),
    description: str = Form(None),
    address: str = Form(None),
    state: str = Form(None),
    unit_type: str = Form(None),
    number_of_units: int = Form(None),
    category: str = Form(None),
    photos: List[UploadFile] = File(None)
):
    """Update an existing building"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # NOTE: renamed from `category` -> `user_category`. The route also has a
        # `category` Form field (the building's rental category), and reusing the
        # same name for the current user's role silently clobbered it, so saved
        # buildings ended up with category="Administrator" instead of the actual
        # value the form submitted.
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        # Get all data
        data = db.get_data()
        buildings = data.get("buildings", [])
        
        # Find the building
        building = None
        building_index = -1
        for idx, b in enumerate(buildings):
            if b.get("_id") == building_id or b.get("id") == building_id:
                building = b
                building_index = idx
                break
        
        if not building:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Building not found"}
            )
        
        # Check if user has permission to edit this building
        if user_category == "Administrator":
            if building.get("created_by") != current_user.get("user_id"):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "You can only edit buildings you created"}
                )
        
        # Update fields
        if name is not None:
            building["name"] = name
        if description is not None:
            building["description"] = description
        if address is not None:
            building["address"] = address
        if state is not None:
            building["state"] = state
        if unit_type is not None:
            building["unit_type"] = unit_type
        if number_of_units is not None:
            building["number_of_units"] = int(number_of_units)
        if category is not None:
            building["category"] = category
        
        # Upload new photos if provided (filter out the empty file part that
        # browsers submit when the file input is left untouched)
        photos = filter_empty_uploads(photos)
        if photos:
            validate_photos(photos)
            photo_urls = []
            for photo in photos:
                try:
                    url = upload_to_firebase(photo, f"buildings/{datetime.now().strftime('%Y%m')}")
                    photo_urls.append(url)
                except Exception as e:
                    logger.error(f"Failed to upload photo: {e}")
            if photo_urls:
                # Keep existing photos and add new ones (limit to MAX_PHOTOS)
                existing_photos = building.get("photos", [])
                all_photos = existing_photos + photo_urls
                building["photos"] = all_photos[:MAX_PHOTOS]
        
        building["updated_at"] = datetime.now().isoformat()
        
        # Update the building in the list
        data["buildings"][building_index] = building
        
        # Save the entire data
        success = db.update_data(data)
        
        if success:
            return JSONResponse({
                "success": True,
                "message": f"Building '{building.get('name')}' updated successfully",
                "building": building
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to update building"}
            )
    
    except HTTPException as e:
        # Preserve the intended status code (e.g. 400 from validate_photos)
        # instead of masking it as a 500.
        logger.warning(f"Update building rejected: {e.detail}")
        return JSONResponse(status_code=e.status_code, content={"success": False, "detail": e.detail})
    except Exception as e:
        logger.error(f"Error updating building: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# UPDATE PROPERTY - SIMPLE FIX
# ============================================
@router.put("/update_property/{property_id}")
async def update_property(
    request: Request,
    property_id: str,
    name: str = Form(None),
    description: str = Form(None),
    building_id: str = Form(None),
    price: float = Form(None),
    visibility: str = Form(None),
    photos: List[UploadFile] = File(None)
):
    """Update an existing property"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        # Get all data
        data = db.get_data()
        properties = data.get("properties", [])
        
        # Find the property
        property_item = None
        property_index = -1
        for idx, p in enumerate(properties):
            if p.get("_id") == property_id or p.get("id") == property_id:
                property_item = p
                property_index = idx
                break
        
        if not property_item:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Property not found"}
            )
        
        # Check if user has permission to edit this property
        if category == "Administrator":
            if property_item.get("created_by") != current_user.get("user_id"):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "You can only edit properties you created"}
                )
        
        # Check if property is occupied
        if property_item.get("occupied_by"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Cannot edit an occupied property. The tenant must be removed first."}
            )
        
        # Update fields
        if name is not None:
            property_item["name"] = name
        if description is not None:
            property_item["description"] = description
        if price is not None:
            property_item["price"] = float(price)
        if visibility is not None:
            property_item["visibility"] = visibility
        
        # Update building reference if changed
        if building_id is not None and building_id != property_item.get("building_id"):
            # Find the new building
            buildings = data.get("buildings", [])
            new_building = None
            for b in buildings:
                if b.get("_id") == building_id or b.get("id") == building_id:
                    new_building = b
                    break
            
            if new_building:
                property_item["building_id"] = building_id
                property_item["building_name"] = new_building.get("name")
                property_item["building_address"] = new_building.get("address")
                property_item["building_state"] = new_building.get("state")
        
        # Upload new photos if provided (filter out the empty file part that
        # browsers submit when the file input is left untouched)
        photos = filter_empty_uploads(photos)
        if photos:
            validate_photos(photos)
            photo_urls = []
            for photo in photos:
                try:
                    url = upload_to_firebase(photo, f"properties/{datetime.now().strftime('%Y%m')}")
                    photo_urls.append(url)
                except Exception as e:
                    logger.error(f"Failed to upload photo: {e}")
            if photo_urls:
                # Keep existing photos and add new ones (limit to MAX_PHOTOS)
                existing_photos = property_item.get("photos", [])
                all_photos = existing_photos + photo_urls
                property_item["photos"] = all_photos[:MAX_PHOTOS]
        
        property_item["updated_at"] = datetime.now().isoformat()
        
        # Update the property in the list
        data["properties"][property_index] = property_item
        
        # Save the entire data
        success = db.update_data(data)
        
        if success:
            return JSONResponse({
                "success": True,
                "message": f"Property '{property_item.get('name')}' updated successfully",
                "property": property_item
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to update property"}
            )
            
    except HTTPException as e:
        # Preserve the intended status code (e.g. 400 from validate_photos)
        # instead of masking it as a 500.
        logger.warning(f"Update property rejected: {e.detail}")
        return JSONResponse(status_code=e.status_code, content={"success": False, "detail": e.detail})
    except Exception as e:
        logger.error(f"Error updating property: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )
    
# ============================================
# GET BUILDING DETAILS FOR EDIT - FIXED
# ============================================
@router.get("/get_building_details/{building_id}")
async def get_building_details(request: Request, building_id: str):
    """Get building details for editing"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        buildings = db.get_collection("buildings")
        building = None
        for b in buildings:
            if b.get("_id") == building_id or b.get("id") == building_id:
                building = b
                break
        
        if not building:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Building not found"}
            )
        
        # Check permission
        if category == "Administrator":
            if building.get("created_by") != current_user.get("user_id"):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "You can only view buildings you created"}
                )
        
        return JSONResponse({
            "success": True,
            "building": building
        })
        
    except Exception as e:
        logger.error(f"Error getting building details: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET PROPERTY DETAILS FOR EDIT - FIXED
# ============================================
@router.get("/get_property_details_for_edit/{property_id}")
async def get_property_details_for_edit(request: Request, property_id: str):
    """Get property details for editing"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        properties = db.get_collection("properties")
        property_item = None
        for p in properties:
            if p.get("_id") == property_id or p.get("id") == property_id:
                property_item = p
                break
        
        if not property_item:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Property not found"}
            )
        
        # Check permission
        if category == "Administrator":
            if property_item.get("created_by") != current_user.get("user_id"):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "You can only view properties you created"}
                )
        
        return JSONResponse({
            "success": True,
            "property": property_item
        })
        
    except Exception as e:
        logger.error(f"Error getting property details: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )
    
# ============================================
# REPORT ENDPOINTS
# ============================================

@router.get("/reports/complaints")
async def get_complaints_report(request: Request):
    """Get all complaints report"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        complaints = db.get_collection("complaints")
        
        # If Administrator, only show complaints for their properties
        if category == "Administrator":
            user_id = current_user.get("user_id")
            # Get properties created by this admin
            properties = db.get_collection("properties")
            admin_property_ids = [p.get("_id") for p in properties if p.get("created_by") == user_id]
            # Filter complaints for these properties
            complaints = [c for c in complaints if c.get("property_id") in admin_property_ids]
        
        # Sort by created_at descending
        complaints.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return JSONResponse({
            "success": True,
            "data": complaints,
            "count": len(complaints)
        })
        
    except Exception as e:
        logger.error(f"Error getting complaints report: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


@router.get("/reports/rents_due")
async def get_rents_due_report(request: Request):
    """Get all rents due for the current month"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        today = datetime.now().date()
        current_month = today.month
        current_year = today.year
        
        users = db.get_collection("users")
        properties = db.get_collection("properties")
        
        # Build property lookup
        property_map = {}
        for p in properties:
            property_map[p.get("_id")] = p
        
        rents_due = []
        
        for user in users:
            if user.get("user_category") == "Tenant" and user.get("tenant_status") == "active":
                rental_end = user.get("rental_end_date")
                if rental_end:
                    try:
                        end_date = datetime.fromisoformat(rental_end).date()
                        # Check if rent is due this month (end date is in current month or past)
                        if end_date.month == current_month and end_date.year == current_year:
                            property_id = user.get("assigned_property_id")
                            property_name = property_map.get(property_id, {}).get("name", "Unknown")
                            rents_due.append({
                                "tenant_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                                "user_id": user.get("user_id"),
                                "property_name": property_name,
                                "amount": user.get("rent_amount", 0),
                                "due_date": rental_end,
                                "status": "due"
                            })
                    except:
                        pass
        
        return JSONResponse({
            "success": True,
            "data": rents_due,
            "count": len(rents_due),
            "summary": f"{len(rents_due)} rent(s) due this month"
        })
        
    except Exception as e:
        logger.error(f"Error getting rents due report: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


@router.get("/reports/pending_rents")
async def get_pending_rents_report(request: Request):
    """Get all overdue/pending rents"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        today = datetime.now().date()
        
        users = db.get_collection("users")
        properties = db.get_collection("properties")
        
        # Build property lookup
        property_map = {}
        for p in properties:
            property_map[p.get("_id")] = p
        
        pending_rents = []
        
        for user in users:
            if user.get("user_category") == "Tenant" and user.get("tenant_status") == "active":
                rental_end = user.get("rental_end_date")
                if rental_end:
                    try:
                        end_date = datetime.fromisoformat(rental_end).date()
                        # Check if rent is overdue (end date is in the past)
                        if end_date < today:
                            property_id = user.get("assigned_property_id")
                            property_name = property_map.get(property_id, {}).get("name", "Unknown")
                            days_overdue = (today - end_date).days
                            pending_rents.append({
                                "tenant_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                                "user_id": user.get("user_id"),
                                "property_name": property_name,
                                "amount": user.get("rent_amount", 0),
                                "due_date": rental_end,
                                "days_overdue": days_overdue,
                                "status": "overdue"
                            })
                    except:
                        pass
        
        # Sort by days overdue (highest first)
        pending_rents.sort(key=lambda x: x.get("days_overdue", 0), reverse=True)
        
        return JSONResponse({
            "success": True,
            "data": pending_rents,
            "count": len(pending_rents),
            "summary": f"{len(pending_rents)} overdue rent(s) totaling ₦{sum(r['amount'] for r in pending_rents):,}"
        })
        
    except Exception as e:
        logger.error(f"Error getting pending rents report: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


@router.get("/reports/paid_rents")
async def get_paid_rents_report(request: Request):
    """Get all paid rents for the current month"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        today = datetime.now().date()
        current_month = today.month
        current_year = today.year
        
        payments = db.get_collection("payments")
        users = db.get_collection("users")
        properties = db.get_collection("properties")
        
        # Build lookups
        user_map = {}
        for u in users:
            user_map[u.get("user_id")] = u
        
        property_map = {}
        for p in properties:
            property_map[p.get("_id")] = p
        
        paid_rents = []
        
        for payment in payments:
            if payment.get("status") == "verified":
                created_at = payment.get("created_at")
                if created_at:
                    try:
                        created_date = datetime.fromisoformat(created_at).date()
                        if created_date.month == current_month and created_date.year == current_year:
                            user_id = payment.get("user_id")
                            property_id = payment.get("property_id")
                            user = user_map.get(user_id, {})
                            property_name = property_map.get(property_id, {}).get("name", "Unknown")
                            paid_rents.append({
                                "tenant_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user_id,
                                "user_id": user_id,
                                "property_name": property_name,
                                "amount": payment.get("amount", 0),
                                "payment_reference": payment.get("payment_reference", "N/A"),
                                "paid_date": created_at,
                                "status": "paid"
                            })
                    except:
                        pass
        
        # Sort by paid date descending
        paid_rents.sort(key=lambda x: x.get("paid_date", ""), reverse=True)
        
        total_paid = sum(r['amount'] for r in paid_rents)
        
        return JSONResponse({
            "success": True,
            "data": paid_rents,
            "count": len(paid_rents),
            "summary": f"{len(paid_rents)} rent(s) paid this month totaling ₦{total_paid:,}"
        })
        
    except Exception as e:
        logger.error(f"Error getting paid rents report: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


@router.get("/reports/additional_expenses")
async def get_additional_expenses_report(request: Request):
    """Get all additional expenses"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        # Get expenses from the data store
        data = db.get_data()
        expenses = data.get("expenses", [])
        
        # If Administrator, filter expenses they created
        if category == "Administrator":
            user_id = current_user.get("user_id")
            expenses = [e for e in expenses if e.get("created_by") == user_id]
        
        # Sort by created_at descending
        expenses.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        total_expenses = sum(e.get("amount", 0) for e in expenses)
        
        return JSONResponse({
            "success": True,
            "data": expenses,
            "count": len(expenses),
            "summary": f"{len(expenses)} expense(s) totaling ₦{total_expenses:,}"
        })
        
    except Exception as e:
        logger.error(f"Error getting additional expenses report: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


@router.get("/reports/pl")
async def get_profit_loss_report(request: Request):
    """Get Profit & Loss report"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        # Get data
        payments = db.get_collection("payments")
        data = db.get_data()
        expenses = data.get("expenses", [])
        
        # Calculate total income (verified payments)
        total_income = sum(p.get("amount", 0) for p in payments if p.get("status") == "verified")
        
        # Calculate total expenses
        total_expenses = sum(e.get("amount", 0) for e in expenses)
        
        # Calculate profit
        profit = total_income - total_expenses
        
        # Build detailed records
        records = []
        
        # Add income records
        for p in payments:
            if p.get("status") == "verified":
                records.append({
                    "category": "Rent Income",
                    "description": f"Payment from {p.get('user_id', 'Unknown')}",
                    "amount": p.get("amount", 0),
                    "type": "income",
                    "date": p.get("created_at", "")
                })
        
        # Add expense records
        for e in expenses:
            records.append({
                "category": e.get("category", "Expense"),
                "description": e.get("description", e.get("name", "Unknown expense")),
                "amount": e.get("amount", 0),
                "type": "expense",
                "date": e.get("created_at", "")
            })
        
        # Sort by date descending
        records.sort(key=lambda x: x.get("date", ""), reverse=True)
        
        return JSONResponse({
            "success": True,
            "data": records,
            "count": len(records),
            "summary": f"Total Income: ₦{total_income:,} | Total Expenses: ₦{total_expenses:,} | Profit: ₦{profit:,}",
            "totals": {
                "income": total_income,
                "expenses": total_expenses,
                "profit": profit
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting P&L report: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        ) 
    
# ============================================
# REPORT ENDPOINTS - AGENTS, BUILDINGS, PROPERTIES
# ============================================

@router.get("/reports/agents")
async def get_agents_report(request: Request):
    """Get all agents report"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        users = db.get_collection("users")
        agents = []
        
        for u in users:
            if u.get("user_category") == "Agent":
                # Get agent's property count
                properties = db.get_collection("properties")
                property_count = len([p for p in properties if p.get("created_by") == u.get("user_id")])
                
                # Get tenant count assigned by this agent
                tenant_count = len([t for t in users if t.get("tenant_assigned_by") == u.get("user_id") and t.get("user_category") == "Tenant"])
                
                agents.append({
                    "user_id": u.get("user_id"),
                    "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("user_id"),
                    "email": u.get("email", ""),
                    "phone": u.get("phone", "N/A"),
                    "property_count": property_count,
                    "tenant_count": tenant_count,
                    "status": u.get("activity_status", "Active"),
                    "created_at": u.get("created_at", ""),
                    "created_by": u.get("created_by", ""),
                    "created_by_name": u.get("created_by_name", "")
                })
        
        # Sort by created_at descending
        agents.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        total_properties = sum(a['property_count'] for a in agents)
        total_tenants = sum(a['tenant_count'] for a in agents)
        
        return JSONResponse({
            "success": True,
            "data": agents,
            "count": len(agents),
            "summary": f"{len(agents)} agent(s) managing {total_properties} properties and {total_tenants} tenant(s)"
        })
        
    except Exception as e:
        logger.error(f"Error getting agents report: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


@router.get("/reports/buildings")
async def get_buildings_report(request: Request):
    """Get all buildings report"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        buildings = db.get_collection("buildings")
        properties = db.get_collection("properties")
        
        # If Administrator, only show buildings they created
        if category == "Administrator":
            user_id = current_user.get("user_id")
            buildings = [b for b in buildings if b.get("created_by") == user_id]
        
        building_data = []
        for b in buildings:
            # Count properties in this building
            prop_count = len([p for p in properties if p.get("building_id") == b.get("_id") or p.get("building_id") == b.get("id")])
            
            # Count available properties
            available_count = len([p for p in properties if (p.get("building_id") == b.get("_id") or p.get("building_id") == b.get("id")) and p.get("available", True)])
            
            # Count occupied properties
            occupied_count = prop_count - available_count
            
            building_data.append({
                "name": b.get("name", "Unknown"),
                "address": b.get("address", "N/A"),
                "state": b.get("state", "N/A"),
                "unit_type": b.get("unit_type", "N/A"),
                "number_of_units": b.get("number_of_units", 0),
                "category": b.get("category", "N/A"),
                "property_count": prop_count,
                "available_count": available_count,
                "occupied_count": occupied_count,
                "created_by": b.get("created_by_name", b.get("created_by", "Unknown")),
                "created_at": b.get("created_at", ""),
                "photos": b.get("photos", [])
            })
        
        # Sort by created_at descending
        building_data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        total_units = sum(b['number_of_units'] for b in building_data)
        total_properties = sum(b['property_count'] for b in building_data)
        
        return JSONResponse({
            "success": True,
            "data": building_data,
            "count": len(building_data),
            "summary": f"{len(building_data)} building(s) with {total_properties} property(ies) and {total_units} total unit(s)"
        })
        
    except Exception as e:
        logger.error(f"Error getting buildings report: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


@router.get("/reports/properties")
async def get_properties_report(request: Request):
    """Get all properties report"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        category = current_user.get("user_category", "")
        if category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        properties = db.get_collection("properties")
        users = db.get_collection("users")
        
        # If Administrator, only show properties they created
        if category == "Administrator":
            user_id = current_user.get("user_id")
            properties = [p for p in properties if p.get("created_by") == user_id]
        
        # Build user lookup for names
        user_map = {}
        for u in users:
            user_map[u.get("user_id")] = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("user_id")
        
        property_data = []
        for p in properties:
            occupied_by = p.get("occupied_by")
            occupant_name = user_map.get(occupied_by, occupied_by or "Vacant")
            
            property_data.append({
                "name": p.get("name", "Unknown"),
                "description": p.get("description", ""),
                "building_name": p.get("building_name", "Unknown Building"),
                "building_address": p.get("building_address", "N/A"),
                "price": p.get("price", 0),
                "visibility": p.get("visibility", "local"),
                "available": p.get("available", True),
                "occupant": occupant_name,
                "occupied_by": occupied_by,
                "created_by": p.get("created_by_name", p.get("created_by", "Unknown")),
                "created_at": p.get("created_at", ""),
                "photos": p.get("photos", [])
            })
        
        # Sort by created_at descending
        property_data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        total_properties = len(property_data)
        available_properties = len([p for p in property_data if p.get("available")])
        occupied_properties = total_properties - available_properties
        total_value = sum(p['price'] for p in property_data)
        
        return JSONResponse({
            "success": True,
            "data": property_data,
            "count": total_properties,
            "summary": f"{total_properties} property(ies): {available_properties} available, {occupied_properties} occupied, Total Value: ₦{total_value:,}"
        })
        
    except Exception as e:
        logger.error(f"Error getting properties report: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )    