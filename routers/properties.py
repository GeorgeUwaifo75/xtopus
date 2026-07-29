from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime, timedelta
import logging
import uuid
import os
import requests

router = APIRouter()
logger = logging.getLogger(__name__)

from database import db
from security import security


# EmailJS Configuration
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


# In properties.py
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
            for key, value in template_params.items():
                if key in ['seller_email', 'to_name', 'name', 'email', 'message', 'subject']:
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
# GET AVAILABLE PROPERTIES WITH AGENT INFO
# ============================================
@router.get("/get_available")
async def get_available_properties(request: Request):
    """Get all available properties with agent info"""
    try:
        all_properties = db.get_collection("properties")
        available_properties = []
        
        # Get all users for agent info lookup
        users = db.get_collection("users")
        user_map = {}
        for u in users:
            user_id = u.get("user_id")
            if user_id:
                user_map[user_id] = {
                    "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or user_id,
                    "phone": u.get("phone", "Not provided"),
                    "email": u.get("email", "Not provided"),
                    "user_category": u.get("user_category", "User")
                }
        
        for p in all_properties:
            if p.get("available", True):
                # Add agent info
                created_by = p.get("created_by")
                agent_info = user_map.get(created_by, {
                    "name": "Property Manager",
                    "phone": "Not provided",
                    "email": "Not provided",
                    "user_category": "Administrator"
                })
                p["agent_name"] = agent_info["name"]
                p["agent_phone"] = agent_info["phone"]
                p["agent_email"] = agent_info["email"]
                p["agent_category"] = agent_info["user_category"]
                available_properties.append(p)
        
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
# GET PROPERTY DETAILS WITH AGENT AND ESCALATION INFO
# ============================================
@router.get("/get_property_details/{property_id}")
async def get_property_details(request: Request, property_id: str):
    """Get detailed information about a property including agent info and escalation contacts"""
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
        
        # Get all users
        users = db.get_collection("users")
        user_map = {}
        for u in users:
            user_id = u.get("user_id")
            if user_id:
                user_map[user_id] = {
                    "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or user_id,
                    "phone": u.get("phone", "Not provided"),
                    "email": u.get("email", "Not provided"),
                    "user_category": u.get("user_category", "User"),
                    "user_id": user_id
                }
        
        # Get the creator (agent/admin) of the property
        created_by = property_item.get("created_by")
        agent_info = user_map.get(created_by, {
            "name": "Property Manager",
            "phone": "Not provided",
            "email": "Not provided",
            "user_category": "Administrator",
            "user_id": created_by
        })
        
        # Build escalation chain
        escalation_contacts = []
        
        # 1st level: Agent (if the creator is an Agent)
        if agent_info.get("user_category") == "Agent":
            escalation_contacts.append({
                "level": 1,
                "role": "Agent",
                "name": agent_info["name"],
                "phone": agent_info["phone"],
                "email": agent_info["email"],
                "user_id": agent_info["user_id"],
                "response_time": "Expected within 3 hours"
            })
            
            # Find the Admin/Sub-Admin who created this agent
            for u in users:
                if u.get("user_id") == created_by:
                    # Check if agent was created by someone
                    created_by_admin = u.get("created_by")
                    if created_by_admin:
                        admin_info = user_map.get(created_by_admin, {})
                        if admin_info:
                            admin_role = admin_info.get("user_category", "Administrator")
                            escalation_contacts.append({
                                "level": 2,
                                "role": admin_role if admin_role in ["Administrator", "Sub-Administrator"] else "Administrator",
                                "name": admin_info.get("name", "Administrator"),
                                "phone": admin_info.get("phone", "Not provided"),
                                "email": admin_info.get("email", "Not provided"),
                                "user_id": admin_info.get("user_id"),
                                "response_time": "Escalated if no response in 3 hours"
                            })
        else:
            # Creator is Admin or Sub-Admin directly
            escalation_contacts.append({
                "level": 1,
                "role": agent_info.get("user_category", "Administrator"),
                "name": agent_info["name"],
                "phone": agent_info["phone"],
                "email": agent_info["email"],
                "user_id": agent_info["user_id"],
                "response_time": "Expected within 3 hours"
            })
        
        # If no escalation contacts found, add a generic admin contact
        if not escalation_contacts:
            # Find any Super Admin
            for u in users:
                if u.get("user_category") == "Super Administrator":
                    escalation_contacts.append({
                        "level": 1,
                        "role": "Super Administrator",
                        "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("user_id"),
                        "phone": u.get("phone", "Not provided"),
                        "email": u.get("email", "Not provided"),
                        "user_id": u.get("user_id"),
                        "response_time": "Expected within 3 hours"
                    })
                    break
        
        # Get chat messages for this property
        chat_data = db.get_data()
        chat_messages = chat_data.get("chat_messages", [])
        property_chats = [m for m in chat_messages if m.get("property_id") == property_id]
        
        # Mark messages as read for current user if they are receiver
        for msg in property_chats:
            if msg.get("receiver_id") == current_user.get("user_id") and not msg.get("read", False):
                msg["read"] = True
        db.update_data(chat_data)
        
        # Get the last 50 messages for display
        recent_chats = property_chats[-50:] if len(property_chats) > 50 else property_chats
        
        return JSONResponse({
            "success": True,
            "property": property_item,
            "agent": agent_info,
            "escalation_contacts": escalation_contacts,
            "chat_messages": recent_chats,
            "chat_count": len(property_chats)
        })
        
    except Exception as e:
        logger.error(f"Error getting property details: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# SEND PROPERTY MESSAGE WITH ESCALATION
# ============================================
@router.post("/send_property_message")
async def send_property_message(request: Request):
    """Send a message about a property with escalation logic"""
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
        
        # Get all users
        users = db.get_collection("users")
        user_map = {}
        for u in users:
            user_id = u.get("user_id")
            if user_id:
                user_map[user_id] = {
                    "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or user_id,
                    "phone": u.get("phone", "Not provided"),
                    "email": u.get("email", "Not provided"),
                    "user_category": u.get("user_category", "User"),
                    "user_id": user_id,
                    "created_by": u.get("created_by")
                }
        
        # Get creator of property
        created_by = property_item.get("created_by")
        agent_info = user_map.get(created_by, {})
        
        # Determine recipients with escalation
        recipients = []
        
        # Primary recipient: Agent or Admin who created the property
        if agent_info:
            recipients.append({
                "user_id": agent_info.get("user_id"),
                "email": agent_info.get("email"),
                "name": agent_info.get("name"),
                "role": agent_info.get("user_category", "Administrator"),
                "level": 1
            })
        
        # Secondary recipients: Admin/Sub-Admin (if agent is primary)
        if agent_info and agent_info.get("user_category") == "Agent":
            created_by_admin = agent_info.get("created_by")
            if created_by_admin:
                admin_info = user_map.get(created_by_admin, {})
                if admin_info:
                    recipients.append({
                        "user_id": admin_info.get("user_id"),
                        "email": admin_info.get("email"),
                        "name": admin_info.get("name"),
                        "role": admin_info.get("user_category", "Administrator"),
                        "level": 2
                    })
        
        # Save the chat message
        chat_data = db.get_data()
        if "chat_messages" not in chat_data:
            chat_data["chat_messages"] = []
        
        chat_message = {
            "_id": f"chat_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}",
            "property_id": property_id,
            "property_name": property_item.get("name"),
            "sender_id": current_user.get("user_id"),
            "sender_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            "sender_email": current_user.get("email", ""),
            "message": message,
            "read": False,
            "escalated": False,
            "escalated_at": None,
            "created_at": datetime.now().isoformat()
        }
        chat_data["chat_messages"].append(chat_message)
        db.update_data(chat_data)
        
        # Send notifications to all recipients
        notification_sent = False
        for recipient in recipients:
            if recipient.get("user_id"):
                # Create notification
                create_notification(
                    recipient.get("user_id"),
                    "property_message",
                    f"💬 New message from {current_user.get('user_id')} about property '{property_item.get('name')}': {message[:50]}...",
                    {
                        "property_id": property_id,
                        "property_name": property_item.get("name"),
                        "sender": current_user.get("user_id"),
                        "message": message,
                        "sender_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip(),
                        "level": recipient.get("level", 1)
                    }
                )
                
                # Send email with EmailJS
                sender_name = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id")
                sender_email = current_user.get("email", "")
                property_name = property_item.get("name")
                recipient_name = recipient.get('name', 'User')
                
                # Create the email body
                email_body = f"""Hello {recipient_name},

You have received a new message about property '{property_name}'.

From: {sender_name} ({sender_email})
Message: {message}

Please login to respond.

Regards,
Xtopus Team"""
                
                # Create template parameters for EmailJS
                # The template expects: seller_email, to_name, name, email, message, subject
                template_params = {
                    'seller_email': recipient.get("email"),  # Recipient email (matches template variable)
                    'to_name': recipient_name,               # Recipient name
                    'name': sender_name,                     # Sender name
                    'email': sender_email,                   # Reply-to email
                    'message': message,                      # The actual message content
                    'subject': f"Xtopus - New Message about {property_name}" ,  # Subject
                    'product_name': property_name
                }
                
                # Send the email
                email_sent = send_emailjs_notification(
                    to_email=recipient.get("email"),
                    subject=f"Xtopus - New Message about {property_name}",
                    body=email_body,
                    template_params=template_params  # Pass the template params
                )
                
                if email_sent:
                    logger.info(f"Email sent to {recipient.get('email')} for property {property_name}")
                else:
                    logger.error(f"Failed to send email to {recipient.get('email')}")
                
                notification_sent = True
        
        # Notify the sender that their message was sent
        create_notification(
            current_user.get("user_id"),
            "property_message_sent",
            f"Your message about '{property_item.get('name')}' has been sent to the agent.",
            {
                "property_id": property_id,
                "property_name": property_item.get("name")
            }
        )
        
        # Generate response with escalation info
        if recipients:
            primary_contact = recipients[0]
            response_message = f"Thank you for your interest in '{property_item.get('name')}'. Your message has been sent to {primary_contact.get('name')} ({primary_contact.get('role')})."
            
            if len(recipients) > 1:
                response_message += f" If you don't receive a response within 3 hours, your message will be escalated to {recipients[1].get('name')} ({recipients[1].get('role')})."
            
            # Add contact info
            response_message += f"\n\nContact Information:\n📞 Phone: {property_item.get('agent_phone', 'Not provided')}\n✉️ Email: {property_item.get('agent_email', 'Not provided')}"
        else:
            response_message = f"Thank you for your interest in '{property_item.get('name')}'. The property manager has been notified and will respond shortly."
        
        return JSONResponse({
            "success": True,
            "message": "Message sent successfully",
            "response": response_message,
            "recipients": len(recipients),
            "escalation_available": len(recipients) > 1
        })
        
    except Exception as e:
        logger.error(f"Error sending property message: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )
    
# ============================================
# ESCALATE CHAT MESSAGE
# ============================================
@router.post("/escalate_chat")
async def escalate_chat(request: Request):
    """Escalate a chat message to the next level"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        body = await request.json()
        chat_id = body.get("chat_id")
        
        if not chat_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Chat ID is required"}
            )
        
        chat_data = db.get_data()
        messages = chat_data.get("chat_messages", [])
        
        target_message = None
        for msg in messages:
            if msg.get("_id") == chat_id:
                target_message = msg
                break
        
        if not target_message:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Message not found"}
            )
        
        # Mark as escalated
        target_message["escalated"] = True
        target_message["escalated_at"] = datetime.now().isoformat()
        target_message["escalated_by"] = current_user.get("user_id")
        
        db.update_data(chat_data)
        
        # Notify the escalation recipients
        property_id = target_message.get("property_id")
        property_name = target_message.get("property_name", "Property")
        sender_name = target_message.get("sender_name", "User")
        message = target_message.get("message", "")
        
        # Find all admins to notify
        users = db.get_collection("users")
        admins = [u for u in users if u.get("user_category") in ["Super Administrator", "Administrator", "Sub-Administrator"]]
        
        for admin in admins:
            create_notification(
                admin.get("user_id"),
                "chat_escalated",
                f"⚠️ Chat escalated: {sender_name} about '{property_name}'. Please respond.",
                {
                    "chat_id": chat_id,
                    "property_id": property_id,
                    "property_name": property_name,
                    "sender": sender_name,
                    "message": message
                }
            )
            
            # Send email
            email_body = f"""
Hello {admin.get('first_name', 'Admin')},

A chat message has been escalated and requires your attention.

Property: {property_name}
From: {sender_name}
Message: {message}

Please login to respond.

Regards,
Xtopus Team
"""
            send_emailjs_notification(
                admin.get("email"),
                f"Xtopus - Escalated Chat: {property_name}",
                email_body
            )
        
        return JSONResponse({
            "success": True,
            "message": "Chat escalated successfully. Administrators have been notified."
        })
        
    except Exception as e:
        logger.error(f"Error escalating chat: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET PROPERTY CHATS
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



#SIMPLIFIED TEST EMAIL 
 
@router.get("/test_email_simple")
async def test_email_simple(request: Request):
    """Simplified test email using the template directly"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Test email to yourself
        test_email = current_user.get("email")
        
        # Direct API call to EmailJS with PUBLIC KEY
        params = {
            'service_id': EMAILJS_SERVICE_ID,
            'template_id': EMAILJS_TEMPLATE_ID,
            'user_id': EMAILJS_PUBLIC_KEY,  # ← Use PUBLIC KEY here
            'template_params': {
                'seller_email': test_email,
                'to_name': current_user.get("first_name", "User"),
                'name': 'Xtopus Test',
                'email': 'geocorpsys@gmail.com',
                'message': 'This is a direct test from Xtopus.',
                'subject': 'Xtopus - Direct Test'
            }
        }
        
        logger.info(f"Direct test to: {test_email}")
        logger.info(f"Using Public Key: {EMAILJS_PUBLIC_KEY}")
        
        response = requests.post(
            EMAILJS_API_URL,
            json=params,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text}")
        
        return JSONResponse({
            "success": response.status_code == 200,
            "status_code": response.status_code,
            "response": response.text,
            "sent_to": test_email,
            "public_key_used": EMAILJS_PUBLIC_KEY
        })
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
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
            send_emailjs_notification(
                agent_user.get("email"),
                f"Xtopus - Property Request: {property_item.get('name')}",
                email_body
            )
        
        # Also notify admins if agent doesn't respond
        admins = [u for u in users if u.get("user_category") in ["Super Administrator", "Administrator", "Sub-Administrator"]]
        for admin in admins:
            if admin.get("user_id") != agent_user.get("user_id"):
                create_notification(
                    admin.get("user_id"),
                    "property_request_escalation",
                    f"📋 Property request from {current_user.get('user_id')} for '{property_item.get('name')}' - Admin notified as backup.",
                    {
                        "property_id": property_id,
                        "property_name": property_item.get("name"),
                        "requester": current_user.get("user_id")
                    }
                )
        
        return JSONResponse({
            "success": True,
            "message": f"Your request for '{property_item.get('name')}' has been sent to the agent. You will be contacted shortly."
        })
        
    except Exception as e:
        logger.error(f"Error requesting property: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )