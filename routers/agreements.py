from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime
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
EMAILJS_USER_ID = os.getenv('EMAILJS_USER_ID', 'geocorpsys@gmail.com')
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


def send_emailjs_notification(to_email: str, subject: str, body: str, template_params: dict = None) -> bool:
    """Send email notification via EmailJS"""
    try:
        if not all([EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, EMAILJS_USER_ID]):
            logger.warning("EmailJS credentials not configured.")
            return False
        
        params = {
            'service_id': EMAILJS_SERVICE_ID,
            'template_id': EMAILJS_TEMPLATE_ID,
            'user_id': EMAILJS_USER_ID,
            'template_params': {
                'to_email': to_email,
                'subject': subject,
                'message': body,
                'from_name': 'Xtopus Property Management',
                'reply_to': 'geocorpsys@gmail.com',
                'project_name': 'Xtopus',
                'company_name': 'GeoCorp Sys'
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


# ============================================
# CREATE AGREEMENT / CONTRACT
# ============================================
@router.post("/create_agreement")
async def create_agreement(request: Request):
    """Create a tenancy agreement/contract"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Check if user has permission
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only Administrators can create agreements"}
            )
        
        body = await request.json()
        property_id = body.get("property_id")
        tenant_id = body.get("tenant_id")
        start_date = body.get("start_date")
        end_date = body.get("end_date")
        rent_amount = body.get("rent_amount")
        terms = body.get("terms")
        
        # Validate required fields
        if not all([property_id, tenant_id, start_date, end_date, rent_amount, terms]):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "All fields are required"}
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
        
        # Find tenant
        users = db.get_collection("users")
        tenant_user = None
        for u in users:
            if u.get("user_id") == tenant_id:
                tenant_user = u
                break
        
        if not tenant_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Tenant not found"}
            )
        
        # Create agreement
        agreement_id = f"agr_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
        
        agreement = {
            "_id": agreement_id,
            "id": agreement_id,
            "property_id": property_id,
            "property_name": property_item.get("name"),
            "tenant_id": tenant_id,
            "tenant_name": f"{tenant_user.get('first_name', '')} {tenant_user.get('last_name', '')}".strip() or tenant_id,
            "tenant_email": tenant_user.get("email"),
            "start_date": start_date,
            "end_date": end_date,
            "rent_amount": float(rent_amount),
            "terms": terms,
            "status": "pending",  # pending, signed, approved, active, expired
            "signed": False,
            "signed_at": None,
            "created_by": current_user.get("user_id"),
            "created_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # Store in database
        data = db.get_data()
        if "agreements" not in data:
            data["agreements"] = []
        data["agreements"].append(agreement)
        success = db.update_data(data)
        
        if success:
            # Update tenant with agreement reference
            for u in users:
                if u.get("user_id") == tenant_id:
                    u["agreement_id"] = agreement_id
                    u["agreement_status"] = "pending"
                    db.update_collection_item("users", u.get("_id"), u)
                    break
            
            # Update property with agreement reference
            for p in properties:
                if p.get("_id") == property_id or p.get("id") == property_id:
                    p["agreement_id"] = agreement_id
                    p["agreement_status"] = "pending"
                    db.update_collection_item("properties", p.get("_id"), p)
                    break
            
            # Notify the tenant
            create_notification(
                tenant_id,
                "agreement_created",
                f"📝 A tenancy agreement for '{property_item.get('name')}' has been created. Please review and sign.",
                {
                    "agreement_id": agreement_id,
                    "property_name": property_item.get("name"),
                    "rent_amount": rent_amount
                }
            )
            
            # Send email to tenant
            email_body = f"""
Hello {tenant_user.get('first_name', 'Tenant')},

A tenancy agreement has been created for the property '{property_item.get('name')}'.

Agreement Details:
- Property: {property_item.get('name')}
- Rental Period: {start_date} to {end_date}
- Monthly Rent: ₦{rent_amount}

Please login to review and sign the agreement.

Regards,
Xtopus Team
"""
            send_emailjs_notification(
                tenant_user.get("email"),
                "Xtopus - Tenancy Agreement Ready for Signing",
                email_body
            )
            
            # Notify the admin
            create_notification(
                current_user.get("user_id"),
                "agreement_created",
                f"✅ Agreement created for {tenant_id} - '{property_item.get('name')}'",
                {
                    "agreement_id": agreement_id,
                    "property_name": property_item.get("name")
                }
            )
            
            return JSONResponse({
                "success": True,
                "message": "Agreement created successfully",
                "agreement": agreement
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to create agreement"}
            )
            
    except Exception as e:
        logger.error(f"Error creating agreement: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# CREATE WARNING LETTER
# ============================================
@router.post("/create_warning")
async def create_warning(request: Request):
    """Create a warning letter for a tenant"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Check if user has permission
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only Administrators can send warnings"}
            )
        
        body = await request.json()
        property_id = body.get("property_id")
        tenant_id = body.get("tenant_id")
        subject = body.get("subject")
        warning_body = body.get("body")
        warning_date = body.get("date")
        
        # Validate required fields
        if not all([property_id, tenant_id, subject, warning_body, warning_date]):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "All fields are required"}
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
        
        # Find tenant
        users = db.get_collection("users")
        tenant_user = None
        for u in users:
            if u.get("user_id") == tenant_id:
                tenant_user = u
                break
        
        if not tenant_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Tenant not found"}
            )
        
        # Create warning letter
        warning_id = f"warn_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
        
        warning = {
            "_id": warning_id,
            "id": warning_id,
            "property_id": property_id,
            "property_name": property_item.get("name"),
            "tenant_id": tenant_id,
            "tenant_name": f"{tenant_user.get('first_name', '')} {tenant_user.get('last_name', '')}".strip() or tenant_id,
            "tenant_email": tenant_user.get("email"),
            "subject": subject,
            "body": warning_body,
            "date": warning_date,
            "status": "sent",
            "created_by": current_user.get("user_id"),
            "created_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            "created_at": datetime.now().isoformat()
        }
        
        # Store in database
        data = db.get_data()
        if "warnings" not in data:
            data["warnings"] = []
        data["warnings"].append(warning)
        success = db.update_data(data)
        
        if success:
            # Notify the tenant
            create_notification(
                tenant_id,
                "warning_received",
                f"⚠️ A warning letter regarding '{property_item.get('name')}' has been issued. Subject: {subject}",
                {
                    "warning_id": warning_id,
                    "property_name": property_item.get("name"),
                    "subject": subject
                }
            )
            
            # Send email to tenant
            email_body = f"""
Hello {tenant_user.get('first_name', 'Tenant')},

A warning letter has been issued regarding your tenancy at '{property_item.get('name')}'.

Subject: {subject}

Message:
{warning_body}

Date: {warning_date}

Please take appropriate action and contact the management if you have any questions.

Regards,
Xtopus Team
"""
            send_emailjs_notification(
                tenant_user.get("email"),
                f"Xtopus - Warning Letter: {subject}",
                email_body
            )
            
            # Notify the admin
            create_notification(
                current_user.get("user_id"),
                "warning_sent",
                f"⚠️ Warning sent to {tenant_id} - Subject: {subject}",
                {
                    "warning_id": warning_id,
                    "tenant_id": tenant_id
                }
            )
            
            return JSONResponse({
                "success": True,
                "message": "Warning letter sent successfully",
                "warning": warning
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to send warning"}
            )
            
    except Exception as e:
        logger.error(f"Error creating warning: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# CREATE EVICTION NOTICE
# ============================================
@router.post("/create_eviction")
async def create_eviction(request: Request):
    """Create an eviction notice for a tenant"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Check if user has permission
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only Administrators can issue eviction notices"}
            )
        
        body = await request.json()
        property_id = body.get("property_id")
        tenant_id = body.get("tenant_id")
        reason = body.get("reason")
        eviction_date = body.get("eviction_date")
        details = body.get("details", "")
        
        # Validate required fields
        if not all([property_id, tenant_id, reason, eviction_date]):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "All required fields must be filled"}
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
        
        # Find tenant
        users = db.get_collection("users")
        tenant_user = None
        for u in users:
            if u.get("user_id") == tenant_id:
                tenant_user = u
                break
        
        if not tenant_user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Tenant not found"}
            )
        
        # Create eviction notice
        eviction_id = f"evict_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
        
        eviction = {
            "_id": eviction_id,
            "id": eviction_id,
            "property_id": property_id,
            "property_name": property_item.get("name"),
            "tenant_id": tenant_id,
            "tenant_name": f"{tenant_user.get('first_name', '')} {tenant_user.get('last_name', '')}".strip() or tenant_id,
            "tenant_email": tenant_user.get("email"),
            "reason": reason,
            "eviction_date": eviction_date,
            "details": details,
            "status": "issued",  # issued, contested, executed
            "created_by": current_user.get("user_id"),
            "created_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            "created_at": datetime.now().isoformat()
        }
        
        # Store in database
        data = db.get_data()
        if "evictions" not in data:
            data["evictions"] = []
        data["evictions"].append(eviction)
        success = db.update_data(data)
        
        if success:
            # Update tenant status
            for u in users:
                if u.get("user_id") == tenant_id:
                    u["eviction_status"] = "issued"
                    u["eviction_id"] = eviction_id
                    u["eviction_date"] = eviction_date
                    db.update_collection_item("users", u.get("_id"), u)
                    break
            
            # Notify the tenant
            create_notification(
                tenant_id,
                "eviction_issued",
                f"🚫 An eviction notice has been issued for '{property_item.get('name')}'. Reason: {reason}",
                {
                    "eviction_id": eviction_id,
                    "property_name": property_item.get("name"),
                    "reason": reason,
                    "eviction_date": eviction_date
                }
            )
            
            # Send email to tenant
            email_body = f"""
Hello {tenant_user.get('first_name', 'Tenant')},

An EVICTION NOTICE has been issued regarding your tenancy at '{property_item.get('name')}'.

Reason for Eviction:
{reason}

Eviction Date: {eviction_date}

Additional Details:
{details or 'No additional details provided.'}

Please take immediate action. If you wish to contest this eviction, please contact management as soon as possible.

Regards,
Xtopus Team
"""
            send_emailjs_notification(
                tenant_user.get("email"),
                f"Xtopus - EVICTION NOTICE: {reason}",
                email_body
            )
            
            # Notify all admins
            admins = [u for u in users if u.get("user_category") in ["Super Administrator", "Administrator"]]
            for admin in admins:
                if admin.get("user_id") != current_user.get("user_id"):
                    create_notification(
                        admin.get("user_id"),
                        "eviction_issued",
                        f"🚫 Eviction notice issued for {tenant_id} - Property: {property_item.get('name')}",
                        {
                            "eviction_id": eviction_id,
                            "tenant_id": tenant_id,
                            "property_name": property_item.get("name")
                        }
                    )
            
            return JSONResponse({
                "success": True,
                "message": "Eviction notice issued successfully",
                "eviction": eviction
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to issue eviction notice"}
            )
            
    except Exception as e:
        logger.error(f"Error creating eviction: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET AGREEMENT STATUS
# ============================================
@router.get("/get_agreement_status/{agreement_id}")
async def get_agreement_status(request: Request, agreement_id: str):
    """Get the status of a specific agreement"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        data = db.get_data()
        agreements = data.get("agreements", [])
        
        agreement = None
        for a in agreements:
            if a.get("_id") == agreement_id or a.get("id") == agreement_id:
                agreement = a
                break
        
        if not agreement:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Agreement not found"}
            )
        
        return JSONResponse({
            "success": True,
            "agreement": agreement
        })
        
    except Exception as e:
        logger.error(f"Error getting agreement status: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# SIGN AGREEMENT (Tenant)
# ============================================
@router.post("/sign_agreement")
async def sign_agreement(request: Request):
    """Tenant signs an agreement"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        body = await request.json()
        agreement_id = body.get("agreement_id")
        
        if not agreement_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Agreement ID is required"}
            )
        
        data = db.get_data()
        agreements = data.get("agreements", [])
        
        agreement = None
        agreement_index = None
        for i, a in enumerate(agreements):
            if a.get("_id") == agreement_id or a.get("id") == agreement_id:
                agreement = a
                agreement_index = i
                break
        
        if not agreement:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Agreement not found"}
            )
        
        # Check if the current user is the tenant
        if agreement.get("tenant_id") != current_user.get("user_id"):
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "You are not authorized to sign this agreement"}
            )
        
        if agreement.get("signed"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "This agreement has already been signed"}
            )
        
        # Update agreement
        agreement["signed"] = True
        agreement["signed_at"] = datetime.now().isoformat()
        agreement["status"] = "signed"
        agreement["updated_at"] = datetime.now().isoformat()
        
        data["agreements"][agreement_index] = agreement
        success = db.update_data(data)
        
        if success:
            # Update user
            users = db.get_collection("users")
            for u in users:
                if u.get("user_id") == current_user.get("user_id"):
                    u["agreement_status"] = "signed"
                    
                    # If rent payment was already confirmed and this tenant
                    # was only waiting on the signature, the assignment is
                    # now complete - finalize activation here.
                    if u.get("tenant_status") == "pending_agreement":
                        u["tenant_status"] = "active"
                        u["tenant_activated_by"] = "System (Agreement Signed)"
                        u["tenant_activated_at"] = datetime.now().isoformat()
                        u["awaiting_agreement_signature"] = False
                        
                        create_notification(
                            u.get("user_id"),
                            "tenant_assignment_completed",
                            f"🎉 Your tenancy for '{agreement.get('property_name')}' is now fully active - payment and agreement are both confirmed."
                        )
                        assigned_by = u.get("tenant_assigned_by")
                        if assigned_by:
                            create_notification(
                                assigned_by,
                                "tenant_assignment_completed",
                                f"✅ {u.get('user_id')} has signed the agreement for '{agreement.get('property_name')}' and their tenancy is now active."
                            )
                    
                    db.update_collection_item("users", u.get("_id"), u)
                    break
            
            # Update property
            properties = db.get_collection("properties")
            property_id = agreement.get("property_id")
            for p in properties:
                if p.get("_id") == property_id or p.get("id") == property_id:
                    p["agreement_status"] = "signed"
                    db.update_collection_item("properties", p.get("_id"), p)
                    break
            
            # Notify the admin
            created_by = agreement.get("created_by")
            if created_by:
                create_notification(
                    created_by,
                    "agreement_signed",
                    f"✅ Tenant {current_user.get('user_id')} has signed the agreement for '{agreement.get('property_name')}'",
                    {
                        "agreement_id": agreement_id,
                        "tenant_id": current_user.get("user_id"),
                        "property_name": agreement.get("property_name")
                    }
                )
            
            return JSONResponse({
                "success": True,
                "message": "Agreement signed successfully",
                "agreement": agreement
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to sign agreement"}
            )
            
    except Exception as e:
        logger.error(f"Error signing agreement: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET ALL AGREEMENTS
# ============================================
@router.get("/get_all_agreements")
async def get_all_agreements(request: Request):
    """Get all agreements for management"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        data = db.get_data()
        agreements = data.get("agreements", [])
        
        return JSONResponse({
            "success": True,
            "agreements": agreements,
            "count": len(agreements)
        })
        
    except Exception as e:
        logger.error(f"Error getting agreements: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )