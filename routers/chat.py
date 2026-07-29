from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
import logging
import uuid
import os
import requests

router = APIRouter()
logger = logging.getLogger(__name__)

from database import db
from security import security

# EmailJS Configuration (same as admin.py)
EMAILJS_SERVICE_ID = os.getenv('EMAILJS_SERVICE_ID', 'service_78wp8b9')
EMAILJS_TEMPLATE_ID = os.getenv('EMAILJS_TEMPLATE_ID', 'template_06fjijo')
EMAILJS_PUBLIC_KEY = os.getenv('EMAILJS_PUBLIC_KEY', 'VGj6eL5SaKXRW2fIi')
EMAILJS_PRIVATE_KEY = os.getenv('EMAILJS_PRIVATE_KEY', 'oogPO4beeg5UpY1k-Y-UA')
EMAILJS_API_URL = 'https://api.emailjs.com/api/v1.0/email/send'




def get_current_user(request: Request):
    """Get current user from session token"""
    token = request.cookies.get("session_token")
    if not token:
        return None
    user_data = security.get_current_user(token)
    if not user_data:
        return None
    return user_data


# In chat.py, update the send_emailjs_notification function:

def send_emailjs_notification(to_email: str, subject: str, body: str, template_params: dict = None) -> bool:
    try:
        if not all([EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, EMAILJS_PUBLIC_KEY]):
            logger.warning("EmailJS credentials not configured.")
            return False
        
        params = {
            'service_id': EMAILJS_SERVICE_ID,
            'template_id': EMAILJS_TEMPLATE_ID,
            'user_id': EMAILJS_PUBLIC_KEY,  # ← Use PUBLIC KEY
            'template_params': {
                'seller_email': to_email,
                'to_name': 'User',
                'name': 'Xtopus Property Management',
                'email': 'geocorpsys@gmail.com',
                'message': body,
                'subject': subject
            }
        }
        
        if template_params:
            params['template_params'].update(template_params)
        
        response = requests.post(EMAILJS_API_URL, json=params, headers={'Content-Type': 'application/json'}, timeout=30)
        if response.status_code == 200:
            logger.info(f"Email sent successfully to {to_email}")
            return True
        else:
            logger.error(f"Failed to send email: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return False

def create_notification(user_id: str, notification_type: str, message: str, related_data: dict = None):
    """Create a notification for a user"""
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


# ============================================
# SEND PROPERTY MESSAGE (Chat)
# ============================================
@router.post("/send_property_message")
async def send_property_message(request: Request):
    """Send a message about a property to the agent"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        body = await request.json()
        property_id = body.get("property_id")
        message = body.get("message")
        
        if not property_id or not message:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Property ID and message are required"}
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
        
        # Get agent (creator of property)
        created_by = property_item.get("created_by")
        agent_user = None
        users = db.get_collection("users")
        for u in users:
            if u.get("user_id") == created_by:
                agent_user = u
                break
        
        # Save the chat message to the database
        chat_data = db.get_data()
        if "chat_messages" not in chat_data:
            chat_data["chat_messages"] = []
        
        chat_message = {
            "_id": f"chat_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}",
            "property_id": property_id,
            "property_name": property_item.get("name"),
            "sender_id": current_user.get("user_id"),
            "sender_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            "receiver_id": created_by,
            "message": message,
            "read": False,
            "created_at": datetime.now().isoformat()
        }
        chat_data["chat_messages"].append(chat_message)
        db.update_data(chat_data)
        
        # Create notification for agent
        if agent_user:
            create_notification(
                agent_user.get("user_id"),
                "property_message",
                f"💬 New message from {current_user.get('user_id')} about property '{property_item.get('name')}': {message[:50]}...",
                {
                    "property_id": property_id,
                    "property_name": property_item.get("name"),
                    "sender": current_user.get("user_id"),
                    "message": message,
                    "sender_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip()
                }
            )
            
            # Send email to agent
            email_body = f"""
        Hello {agent_user.get('first_name', 'Agent')},
        
        You have received a new message about your property '{property_item.get('name')}'.
        
        From: {current_user.get('user_id')} ({current_user.get('first_name', '')} {current_user.get('last_name', '')})
        Message: {message}
        
        Please login to respond.
        
        Regards,
        Xtopus Team
        """
        
        # Add template_params with product_name
        template_params = {
            'seller_email': agent_user.get("email"),
            'to_name': agent_user.get('first_name', 'Agent'),
            'name': f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            'email': current_user.get("email", ""),
            'message': message,
            'subject': f"Xtopus - New Message about {property_item.get('name')}",
            'product_name': property_item.get('name')  # ← ADD THIS
        }
        
        send_emailjs_notification(
            agent_user.get("email"),
            f"Xtopus - New Message about {property_item.get('name')}",
            email_body,
            template_params  # Pass the template params
        )
        # Also notify the user that their message was sent
        create_notification(
            current_user.get("user_id"),
            "property_message_sent",
            f"Your message about '{property_item.get('name')}' has been sent to the agent.",
            {
                "property_id": property_id,
                "property_name": property_item.get("name")
            }
        )
        
        # Auto-response (simulated)
        auto_response = f"Thank you for your interest in '{property_item.get('name')}'. The agent has been notified and will respond to you shortly. You can also contact them directly at the number provided."
        
        return JSONResponse({
            "success": True,
            "message": "Message sent successfully",
            "response": auto_response
        })
        
    except Exception as e:
        logger.error(f"Error sending property message: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET CHAT MESSAGES FOR A PROPERTY
# ============================================
@router.get("/get_property_chats/{property_id}")
async def get_property_chats(request: Request, property_id: str):
    """Get all chat messages for a specific property"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        chat_data = db.get_data()
        messages = chat_data.get("chat_messages", [])
        
        # Filter messages for this property
        property_messages = [m for m in messages if m.get("property_id") == property_id]
        
        # Mark messages as read for the current user (if they are the receiver)
        for msg in property_messages:
            if msg.get("receiver_id") == current_user.get("user_id") and not msg.get("read", False):
                msg["read"] = True
        
        # Update the database with read status
        db.update_data(chat_data)
        
        return JSONResponse({
            "success": True,
            "messages": property_messages,
            "count": len(property_messages)
        })
        
    except Exception as e:
        logger.error(f"Error getting property chats: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET UNREAD CHAT COUNT FOR USER
# ============================================
@router.get("/get_unread_chat_count")
async def get_unread_chat_count(request: Request):
    """Get count of unread chat messages for the current user"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        chat_data = db.get_data()
        messages = chat_data.get("chat_messages", [])
        
        # Count unread messages where current user is the receiver
        unread_count = sum(1 for m in messages 
                          if m.get("receiver_id") == current_user.get("user_id") 
                          and not m.get("read", False))
        
        return JSONResponse({
            "success": True,
            "unread_count": unread_count
        })
        
    except Exception as e:
        logger.error(f"Error getting unread chat count: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# MARK CHAT AS READ
# ============================================
@router.post("/mark_chat_read")
async def mark_chat_read(request: Request):
    """Mark a specific chat message as read"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        body = await request.json()
        message_id = body.get("message_id")
        
        if not message_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Message ID is required"}
            )
        
        chat_data = db.get_data()
        messages = chat_data.get("chat_messages", [])
        
        for msg in messages:
            if msg.get("_id") == message_id:
                msg["read"] = True
                db.update_data(chat_data)
                return JSONResponse({
                    "success": True,
                    "message": "Message marked as read"
                })
        
        return JSONResponse(
            status_code=404,
            content={"success": False, "detail": "Message not found"}
        )
        
    except Exception as e:
        logger.error(f"Error marking chat as read: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET ALL CHATS FOR USER
# ============================================
@router.get("/get_user_chats")
async def get_user_chats(request: Request):
    """Get all chat conversations for the current user"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        chat_data = db.get_data()
        messages = chat_data.get("chat_messages", [])
        
        # Get all messages where current user is either sender or receiver
        user_messages = [m for m in messages 
                        if m.get("sender_id") == current_user.get("user_id") 
                        or m.get("receiver_id") == current_user.get("user_id")]
        
        # Group by property
        property_chats = {}
        for msg in user_messages:
            prop_id = msg.get("property_id")
            if prop_id not in property_chats:
                property_chats[prop_id] = {
                    "property_id": prop_id,
                    "property_name": msg.get("property_name", "Unknown Property"),
                    "messages": [],
                    "last_message": msg.get("created_at"),
                    "unread_count": 0
                }
            property_chats[prop_id]["messages"].append(msg)
            if msg.get("receiver_id") == current_user.get("user_id") and not msg.get("read", False):
                property_chats[prop_id]["unread_count"] += 1
        
        # Convert to list and sort by last message
        chat_list = list(property_chats.values())
        chat_list.sort(key=lambda x: x["last_message"], reverse=True)
        
        return JSONResponse({
            "success": True,
            "chats": chat_list,
            "count": len(chat_list)
        })
        
    except Exception as e:
        logger.error(f"Error getting user chats: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )