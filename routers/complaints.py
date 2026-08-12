from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime, timedelta
import logging
import uuid
import threading
import time

router = APIRouter()
logger = logging.getLogger(__name__)

from database import db
from security import security

# ============================================
# ESCALATION CHECKER (Background Thread)
# ============================================

def check_and_escalate_complaints():
    """Background task to check for complaints that need escalation after 3 days"""
    while True:
        try:
            time.sleep(60)
            logger.info("Checking for complaints that need escalation...")
            
            complaints = db.get_collection("complaints")
            current_time = datetime.now()
            
            for complaint in complaints:
                if complaint.get("status") == "unattended":
                    created_at = complaint.get("created_at")
                    if created_at:
                        try:
                            created_dt = datetime.fromisoformat(created_at)
                            time_diff = current_time - created_dt
                            
                            if time_diff >= timedelta(days=3):
                                if not complaint.get("escalated"):
                                    assignee_id = complaint.get("assignee_id")
                                    users = db.get_collection("users")
                                    
                                    property_id = complaint.get("property_id")
                                    properties = db.get_collection("properties")
                                    property_item = None
                                    for p in properties:
                                        if p.get("_id") == property_id or p.get("id") == property_id:
                                            property_item = p
                                            break
                                    
                                    if property_item:
                                        admin_id = property_item.get("created_by")
                                        if admin_id:
                                            admin_user = None
                                            for u in users:
                                                if u.get("user_id") == admin_id:
                                                    admin_user = u
                                                    break
                                            
                                            if admin_user:
                                                admin_name = f"{admin_user.get('first_name', '')} {admin_user.get('last_name', '')}".strip() or admin_id
                                                
                                                complaint["assignee_id"] = admin_id
                                                complaint["assignee_name"] = admin_name
                                                complaint["escalated"] = True
                                                complaint["escalation_level"] = 1
                                                complaint["escalated_at"] = datetime.now().isoformat()
                                                complaint["escalation_reason"] = "Auto-escalated after 3 days of no response"
                                                complaint["updated_at"] = datetime.now().isoformat()
                                                
                                                if "escalation_history" not in complaint:
                                                    complaint["escalation_history"] = []
                                                complaint["escalation_history"].append({
                                                    "from": assignee_id,
                                                    "to": admin_id,
                                                    "reason": "Auto-escalated after 3 days of no response",
                                                    "timestamp": datetime.now().isoformat()
                                                })
                                                
                                                data = db.get_data()
                                                for idx, c in enumerate(data.get("complaints", [])):
                                                    if c.get("_id") == complaint.get("_id"):
                                                        data["complaints"][idx] = complaint
                                                        db.update_data(data)
                                                        break
                                                
                                                create_notification(
                                                    admin_id,
                                                    "complaint_escalated",
                                                    f"⚠️ Complaint '{complaint.get('subject')}' has been escalated to you after 3 days of no response.",
                                                    {
                                                        "complaint_id": complaint.get("_id"),
                                                        "subject": complaint.get("subject"),
                                                        "tenant_id": complaint.get("tenant_id")
                                                    }
                                                )
                                                
                                                create_notification(
                                                    complaint.get("tenant_id"),
                                                    "complaint_escalated",
                                                    f"⚠️ Your complaint '{complaint.get('subject')}' has been escalated to an Administrator after 3 days.",
                                                    {
                                                        "complaint_id": complaint.get("_id"),
                                                        "subject": complaint.get("subject")
                                                    }
                                                )
                                                
                                                logger.info(f"Complaint {complaint.get('_id')} escalated from {assignee_id} to {admin_id}")
                                                
                        except Exception as e:
                            logger.error(f"Error processing escalation for complaint {complaint.get('_id')}: {e}")
                                
        except Exception as e:
            logger.error(f"Error in escalation checker: {e}")

def start_escalation_checker():
    thread = threading.Thread(target=check_and_escalate_complaints, daemon=True)
    thread.start()
    logger.info("Escalation checker started")

# ============================================
# HELPER FUNCTIONS
# ============================================

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

def record_expense(description: str, amount: float, category: str, complaint_id: str, created_by: str):
    """Record an expense for P&L reporting"""
    data = db.get_data()
    if "expenses" not in data:
        data["expenses"] = []
    
    expense = {
        "_id": f"exp_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}",
        "description": description,
        "amount": amount,
        "category": category,
        "complaint_id": complaint_id,
        "created_by": created_by,
        "created_at": datetime.now().isoformat(),
        "status": "verified"
    }
    data["expenses"].append(expense)
    db.update_data(data)
    return True

def is_complaint_visible_to_user(complaint: dict, user_id: str) -> bool:
    """
    Check if a complaint is visible to a user.
    A complaint is visible if:
    1. User is the tenant who created it
    2. User is the assignee
    3. User is a Super Administrator or Administrator
    4. User is a Sub-Administrator and the assignee is their child
    5. User is an Agent and the assignee is their parent
    """
    assignee_id = complaint.get("assignee_id")
    tenant_id = complaint.get("tenant_id")
    
    # User can see complaints they created (as tenant)
    if tenant_id == user_id:
        return True
    
    # User can see complaints assigned to them
    if assignee_id == user_id:
        return True
    
    # Get user info
    users = db.get_collection("users")
    current_user = None
    for u in users:
        if u.get("user_id") == user_id:
            current_user = u
            break
    
    if not current_user:
        return False
    
    user_category = current_user.get("user_category", "User")
    
    # Super Administrators and Administrators can see all complaints
    if user_category in ["Super Administrator", "Administrator"]:
        return True
    
    # Sub-Administrator: can see complaints assigned to their children
    if user_category == "Sub-Administrator":
        for u in users:
            if u.get("created_by") == user_id:
                if u.get("user_id") == assignee_id:
                    return True
                for u2 in users:
                    if u2.get("created_by") == u.get("user_id") and u2.get("user_id") == assignee_id:
                        return True
    
    # Agent: can see complaints assigned to their parent
    if user_category == "Agent":
        created_by = current_user.get("created_by")
        if created_by == assignee_id:
            return True
    
    # Check if user is the property creator
    property_id = complaint.get("property_id")
    if property_id:
        properties = db.get_collection("properties")
        for p in properties:
            if p.get("_id") == property_id or p.get("id") == property_id:
                if p.get("created_by") == user_id:
                    return True
                break
    
    return False

# ============================================
# GET ASSIGNEES FOR COMPLAINT DROPDOWN
# ============================================
@router.get("/get_assignees")
async def get_assignees(request: Request):
    """Get list of users who can be assigned complaints"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        if current_user.get("user_category") != "Tenant":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only tenants can create complaints"}
            )
        
        users = db.get_collection("users")
        properties = db.get_collection("properties")
        assignees = []
        
        assigned_property_id = current_user.get("assigned_property_id")
        property_creator = None
        
        if assigned_property_id:
            for p in properties:
                if p.get("_id") == assigned_property_id or p.get("id") == assigned_property_id:
                    property_creator = p.get("created_by")
                    break
        
        for user in users:
            user_category = user.get("user_category", "")
            if user_category in ["Agent", "Sub-Administrator", "Administrator", "Super Administrator"]:
                is_relevant = False
                
                if property_creator and user.get("user_id") == property_creator:
                    is_relevant = True
                
                if user_category in ["Super Administrator", "Administrator"]:
                    is_relevant = True
                
                if not is_relevant and property_creator:
                    if user.get("created_by") == property_creator:
                        is_relevant = True
                
                if is_relevant:
                    assignees.append({
                        "user_id": user.get("user_id"),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                        "user_category": user_category,
                        "email": user.get("email", "")
                    })
        
        if not assignees:
            for user in users:
                user_category = user.get("user_category", "")
                if user_category in ["Agent", "Sub-Administrator", "Administrator", "Super Administrator"]:
                    assignees.append({
                        "user_id": user.get("user_id"),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                        "user_category": user_category,
                        "email": user.get("email", "")
                    })
        
        return JSONResponse({
            "success": True,
            "assignees": assignees
        })
        
    except Exception as e:
        logger.error(f"Error getting assignees: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# CREATE COMPLAINT (Tenant) - FIXED
# ============================================
@router.post("/create")
async def create_complaint(request: Request):
    """Create a new complaint"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        if current_user.get("user_category") != "Tenant":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only tenants can create complaints"}
            )
        
        body = await request.json()
        subject = body.get("subject")
        description = body.get("description")
        assignee_id = body.get("assignee_id")
        priority = body.get("priority", "medium")
        
        if not subject or not description or not assignee_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Subject, description, and assignee are required"}
            )
        
        valid_priorities = ["low", "medium", "high", "emergency"]
        if priority not in valid_priorities:
            priority = "medium"
        
        users = db.get_collection("users")
        assignee = None
        for u in users:
            if u.get("user_id") == assignee_id:
                assignee = u
                break
        
        if not assignee:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Assignee not found"}
            )
        
        property_id = current_user.get("assigned_property_id")
        
        # Log the complaint creation
        logger.info(f"Creating complaint for tenant {current_user.get('user_id')} assigned to {assignee_id}")
        logger.info(f"Property ID: {property_id}")
        
        complaint = {
            "_id": f"comp_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}",
            "tenant_id": current_user.get("user_id"),
            "tenant_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            "assignee_id": assignee_id,
            "assignee_name": f"{assignee.get('first_name', '')} {assignee.get('last_name', '')}".strip() or assignee_id,
            "property_id": property_id,
            "subject": subject,
            "description": description,
            "priority": priority,
            "status": "unattended",
            "cost": 0,
            "admin_comment": "",
            "resolved": None,
            "escalated": False,
            "escalation_level": 0,
            "escalated_at": None,
            "escalation_reason": None,
            "escalation_history": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        success = db.add_to_collection("complaints", complaint)
        
        if success:
            logger.info(f"Complaint created successfully with ID: {complaint['_id']}")
            
            create_notification(
                assignee_id,
                "complaint_assigned",
                f"📋 New complaint from {complaint['tenant_name']}: {subject}",
                {
                    "complaint_id": complaint["_id"],
                    "subject": subject,
                    "tenant_id": current_user.get("user_id"),
                    "priority": priority
                }
            )
            
            create_notification(
                current_user.get("user_id"),
                "complaint_submitted",
                f"✅ Your complaint '{subject}' has been submitted and assigned to {complaint['assignee_name']}.",
                {
                    "complaint_id": complaint["_id"],
                    "subject": subject
                }
            )
            
            return JSONResponse({
                "success": True,
                "message": "Complaint submitted successfully",
                "complaint": complaint
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to create complaint"}
            )
            
    except Exception as e:
        logger.error(f"Error creating complaint: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET MY COMPLAINTS (Tenant)
# ============================================
@router.get("/my")
async def get_my_complaints(request: Request):
    """Get all complaints for the current tenant"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        if current_user.get("user_category") != "Tenant":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only tenants can view their complaints"}
            )
        
        complaints = db.get_collection("complaints")
        user_complaints = [c for c in complaints if c.get("tenant_id") == current_user.get("user_id")]
        
        user_complaints.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return JSONResponse({
            "success": True,
            "complaints": user_complaints,
            "count": len(user_complaints)
        })
        
    except Exception as e:
        logger.error(f"Error getting my complaints: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET COMPLAINT BY ID
# ============================================
@router.get("/{complaint_id}")
async def get_complaint(request: Request, complaint_id: str):
    """Get a specific complaint by ID"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        complaints = db.get_collection("complaints")
        complaint = None
        for c in complaints:
            if c.get("_id") == complaint_id:
                complaint = c
                break
        
        if not complaint:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Complaint not found"}
            )
        
        user_id = current_user.get("user_id")
        user_category = current_user.get("user_category", "")
        
        if user_category == "Super Administrator":
            return JSONResponse({
                "success": True,
                "complaint": complaint
            })
        
        if not is_complaint_visible_to_user(complaint, user_id):
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "You don't have permission to view this complaint"}
            )
        
        return JSONResponse({
            "success": True,
            "complaint": complaint
        })
        
    except Exception as e:
        logger.error(f"Error getting complaint: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET ASSIGNED COMPLAINTS - FIXED
# ============================================
@router.get("/assigned")
async def get_assigned_complaints(
    request: Request,
    status: Optional[str] = None,
    priority: Optional[str] = None
):
    """Get complaints visible to the current user"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        user_category = current_user.get("user_category", "")
        user_id = current_user.get("user_id")
        
        logger.info(f"===== GET ASSIGNED COMPLAINTS =====")
        logger.info(f"User ID: {user_id}, Category: {user_category}")
        
        if user_category not in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent", "Tenant"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        all_complaints = db.get_collection("complaints")
        logger.info(f"Total complaints in DB: {len(all_complaints)}")
        
        visible_complaints = []
        
        for complaint in all_complaints:
            complaint_id = complaint.get("_id")
            complaint_assignee = complaint.get("assignee_id")
            complaint_tenant = complaint.get("tenant_id")
            
            is_visible = is_complaint_visible_to_user(complaint, user_id)
            
            if is_visible:
                logger.info(f"✅ Complaint {complaint_id} is VISIBLE - assignee: {complaint_assignee}, tenant: {complaint_tenant}")
                visible_complaints.append(complaint)
            else:
                logger.info(f"❌ Complaint {complaint_id} is NOT VISIBLE - assignee: {complaint_assignee}, tenant: {complaint_tenant}")
        
        logger.info(f"Visible complaints: {len(visible_complaints)}")
        
        if status and status != "all":
            visible_complaints = [c for c in visible_complaints if c.get("status") == status]
        
        if priority and priority != "all":
            visible_complaints = [c for c in visible_complaints if c.get("priority") == priority]
        
        priority_order = {"emergency": 0, "high": 1, "medium": 2, "low": 3}
        status_order = {"unattended": 0, "contacted": 1, "in_progress": 2, "completed": 3, "resolved": 4, "not_resolved": 5}
        
        visible_complaints.sort(key=lambda x: (
            priority_order.get(x.get("priority", "medium"), 2),
            status_order.get(x.get("status", "unattended"), 0),
            x.get("created_at", "")
        ))
        
        return JSONResponse({
            "success": True,
            "complaints": visible_complaints,
            "count": len(visible_complaints),
            "user_role": user_category,
            "debug": {
                "total_complaints": len(all_complaints),
                "visible_count": len(visible_complaints)
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting assigned complaints: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# UPDATE COMPLAINT (Admin/Agent)
# ============================================
@router.put("/{complaint_id}")
async def update_complaint(request: Request, complaint_id: str):
    """Update a complaint (status, cost, comment)"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        user_category = current_user.get("user_category", "")
        user_id = current_user.get("user_id")
        
        if user_category not in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        complaints = db.get_collection("complaints")
        complaint = None
        complaint_index = -1
        for idx, c in enumerate(complaints):
            if c.get("_id") == complaint_id:
                complaint = c
                complaint_index = idx
                break
        
        if not complaint:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Complaint not found"}
            )
        
        assignee_id = complaint.get("assignee_id")
        property_id = complaint.get("property_id")
        
        can_update = False
        
        if user_id == assignee_id:
            can_update = True
        
        if user_category == "Super Administrator":
            can_update = True
        
        if property_id:
            properties = db.get_collection("properties")
            for p in properties:
                if p.get("_id") == property_id or p.get("id") == property_id:
                    if p.get("created_by") == user_id:
                        can_update = True
                    break
        
        if not can_update:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "You don't have permission to update this complaint"}
            )
        
        body = await request.json()
        new_status = body.get("status")
        cost = body.get("cost")
        admin_comment = body.get("admin_comment")
        
        valid_statuses = ["unattended", "contacted", "in_progress", "completed"]
        if new_status and new_status not in valid_statuses:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}
            )
        
        if new_status:
            complaint["status"] = new_status
            if new_status != "unattended":
                complaint["escalated"] = False
                complaint["escalation_level"] = 0
        
        if cost is not None:
            complaint["cost"] = float(cost)
        
        if admin_comment is not None:
            complaint["admin_comment"] = admin_comment
        
        complaint["updated_at"] = datetime.now().isoformat()
        
        data = db.get_data()
        data["complaints"][complaint_index] = complaint
        success = db.update_data(data)
        
        if success:
            tenant_id = complaint.get("tenant_id")
            if tenant_id:
                status_labels = {
                    "unattended": "Unattended",
                    "contacted": "Contacted Tenant",
                    "in_progress": "In Progress",
                    "completed": "Completed - Awaiting Your Confirmation"
                }
                status_label = status_labels.get(complaint.get("status"), complaint.get("status"))
                
                if complaint.get("status") == "completed":
                    message = f"📋 Your complaint '{complaint.get('subject')}' has been marked as COMPLETED. Please confirm if it has been resolved."
                    notification_type = "complaint_completed"
                else:
                    message = f"📋 Your complaint '{complaint.get('subject')}' has been updated to: {status_label}"
                    notification_type = "complaint_updated"
                
                if admin_comment:
                    message += f"\n\nNote: {admin_comment}"
                if complaint.get("cost", 0) > 0:
                    message += f"\n\n💰 Cost: ₦{complaint.get('cost', 0)}"
                
                create_notification(
                    tenant_id,
                    notification_type,
                    message,
                    {
                        "complaint_id": complaint_id,
                        "status": complaint.get("status"),
                        "cost": complaint.get("cost", 0)
                    }
                )
            
            if complaint.get("cost", 0) > 0 and complaint.get("status") == "completed":
                expense_description = f"Complaint Resolution: {complaint.get('subject', 'Unknown')}"
                record_expense(
                    description=expense_description,
                    amount=complaint.get("cost", 0),
                    category="Complaint Resolution",
                    complaint_id=complaint_id,
                    created_by=current_user.get("user_id")
                )
                logger.info(f"Expense recorded for complaint {complaint_id}: ₦{complaint.get('cost', 0)}")
            
            return JSONResponse({
                "success": True,
                "message": "Complaint updated successfully",
                "complaint": complaint
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to update complaint"}
            )
            
    except Exception as e:
        logger.error(f"Error updating complaint: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# CONFIRM RESOLUTION (Tenant)
# ============================================
@router.post("/confirm_resolution")
async def confirm_resolution(request: Request):
    """Tenant confirms if a complaint has been resolved"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        if current_user.get("user_category") != "Tenant":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only tenants can confirm resolution"}
            )
        
        body = await request.json()
        complaint_id = body.get("complaint_id")
        resolved = body.get("resolved")
        
        if not complaint_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Complaint ID is required"}
            )
        
        if resolved is None:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Resolved status is required (true/false)"}
            )
        
        complaints = db.get_collection("complaints")
        complaint = None
        complaint_index = -1
        for idx, c in enumerate(complaints):
            if c.get("_id") == complaint_id:
                complaint = c
                complaint_index = idx
                break
        
        if not complaint:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Complaint not found"}
            )
        
        if complaint.get("tenant_id") != current_user.get("user_id"):
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "You can only confirm resolution for your own complaints"}
            )
        
        if complaint.get("status") != "completed":
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Complaint must be in 'completed' status before confirming resolution"}
            )
        
        complaint["resolved"] = resolved
        if resolved:
            complaint["status"] = "resolved"
        else:
            complaint["status"] = "not_resolved"
        complaint["updated_at"] = datetime.now().isoformat()
        
        data = db.get_data()
        data["complaints"][complaint_index] = complaint
        success = db.update_data(data)
        
        if success:
            assignee_id = complaint.get("assignee_id")
            if assignee_id:
                resolution_status = "✅ RESOLVED" if resolved else "❌ NOT RESOLVED"
                create_notification(
                    assignee_id,
                    "complaint_resolution_confirmed",
                    f"📋 Tenant has confirmed complaint '{complaint.get('subject')}' as: {resolution_status}",
                    {
                        "complaint_id": complaint_id,
                        "resolved": resolved,
                        "tenant_id": current_user.get("user_id")
                    }
                )
            
            if resolved:
                property_id = complaint.get("property_id")
                if property_id:
                    properties = db.get_collection("properties")
                    for p in properties:
                        if p.get("_id") == property_id or p.get("id") == property_id:
                            admin_id = p.get("created_by")
                            if admin_id:
                                create_notification(
                                    admin_id,
                                    "complaint_resolved",
                                    f"✅ Complaint '{complaint.get('subject')}' has been confirmed as RESOLVED by the tenant.",
                                    {
                                        "complaint_id": complaint_id,
                                        "tenant_id": current_user.get("user_id")
                                    }
                                )
                            break
            
            return JSONResponse({
                "success": True,
                "message": f"Complaint marked as {'resolved' if resolved else 'not resolved'}",
                "complaint": complaint
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to update complaint"}
            )
            
    except Exception as e:
        logger.error(f"Error confirming resolution: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# GET COMPLAINT STATS - FIXED
# ============================================
@router.get("/stats")
async def get_complaint_stats(request: Request):
    """Get complaint statistics for dashboard"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        user_category = current_user.get("user_category", "")
        user_id = current_user.get("user_id")
        
        if user_category not in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent", "Tenant"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        all_complaints = db.get_collection("complaints")
        visible_complaints = []
        
        for c in all_complaints:
            if is_complaint_visible_to_user(c, user_id):
                visible_complaints.append(c)
        
        stats = {
            "total": len(visible_complaints),
            "unattended": len([c for c in visible_complaints if c.get("status") == "unattended"]),
            "contacted": len([c for c in visible_complaints if c.get("status") == "contacted"]),
            "in_progress": len([c for c in visible_complaints if c.get("status") == "in_progress"]),
            "completed": len([c for c in visible_complaints if c.get("status") == "completed"]),
            "resolved": len([c for c in visible_complaints if c.get("status") == "resolved"]),
            "not_resolved": len([c for c in visible_complaints if c.get("status") == "not_resolved"]),
            "escalated": len([c for c in visible_complaints if c.get("escalated") == True])
        }
        
        return JSONResponse({
            "success": True,
            "stats": stats
        })
        
    except Exception as e:
        logger.error(f"Error getting complaint stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )

# ============================================
# DEBUG: GET ALL COMPLAINTS (Super Admin only)
# ============================================
@router.get("/debug/all")
async def debug_all_complaints(request: Request):
    """DEBUG: Get all complaints with full details"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        if current_user.get("user_category") != "Super Administrator":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        complaints = db.get_collection("complaints")
        users = db.get_collection("users")
        
        user_map = {}
        for u in users:
            user_map[u.get("user_id")] = {
                "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("user_id"),
                "category": u.get("user_category", "Unknown")
            }
        
        result = []
        for c in complaints:
            result.append({
                "id": c.get("_id"),
                "subject": c.get("subject"),
                "tenant_id": c.get("tenant_id"),
                "tenant_name": c.get("tenant_name"),
                "assignee_id": c.get("assignee_id"),
                "assignee_name": c.get("assignee_name"),
                "assignee_info": user_map.get(c.get("assignee_id"), {}),
                "tenant_info": user_map.get(c.get("tenant_id"), {}),
                "property_id": c.get("property_id"),
                "status": c.get("status"),
                "priority": c.get("priority"),
                "escalated": c.get("escalated", False),
                "escalation_level": c.get("escalation_level", 0),
                "created_at": c.get("created_at"),
                "updated_at": c.get("updated_at")
            })
        
        return JSONResponse({
            "success": True,
            "total": len(result),
            "complaints": result
        })
        
    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )