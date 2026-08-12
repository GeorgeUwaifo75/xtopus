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
# ESCALATION CHECKER (Background Thread) - FIXED
# ============================================

def check_and_escalate_complaints():
    """Background task to check for complaints that need escalation after 3 days"""
    while True:
        try:
            time.sleep(60)  # Check every minute
            logger.info("Checking for complaints that need escalation...")
            
            complaints = db.get_collection("complaints")
            current_time = datetime.now()
            
            for complaint in complaints:
                # Check if complaint is still in "unattended" status
                if complaint.get("status") == "unattended":
                    created_at = complaint.get("created_at")
                    if created_at:
                        try:
                            created_dt = datetime.fromisoformat(created_at)
                            time_diff = current_time - created_dt
                            
                            # Check if 3 days (72 hours) have passed
                            if time_diff >= timedelta(days=3):
                                # Check if already escalated
                                if not complaint.get("escalated"):
                                    # Get the current assignee
                                    assignee_id = complaint.get("assignee_id")
                                    users = db.get_collection("users")
                                    
                                    # Find the property creator (Administrator)
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
                                            # Find the admin user
                                            admin_user = None
                                            for u in users:
                                                if u.get("user_id") == admin_id:
                                                    admin_user = u
                                                    break
                                            
                                            if admin_user:
                                                # Escalate to the administrator
                                                admin_name = f"{admin_user.get('first_name', '')} {admin_user.get('last_name', '')}".strip() or admin_id
                                                
                                                # Update complaint
                                                complaint["assignee_id"] = admin_id
                                                complaint["assignee_name"] = admin_name
                                                complaint["escalated"] = True
                                                complaint["escalation_level"] = 1
                                                complaint["escalated_at"] = datetime.now().isoformat()
                                                complaint["escalation_reason"] = "Auto-escalated after 3 days of no response"
                                                complaint["updated_at"] = datetime.now().isoformat()
                                                
                                                # Add escalation history
                                                if "escalation_history" not in complaint:
                                                    complaint["escalation_history"] = []
                                                complaint["escalation_history"].append({
                                                    "from": assignee_id,
                                                    "to": admin_id,
                                                    "reason": "Auto-escalated after 3 days of no response",
                                                    "timestamp": datetime.now().isoformat()
                                                })
                                                
                                                # Save to database
                                                data = db.get_data()
                                                for idx, c in enumerate(data.get("complaints", [])):
                                                    if c.get("_id") == complaint.get("_id"):
                                                        data["complaints"][idx] = complaint
                                                        db.update_data(data)
                                                        break
                                                
                                                # Notify the new assignee
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
                                                
                                                # Notify the tenant
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

# Start the escalation checker in a background thread
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
        logger.warning("No session token found in cookies")
        return None
    user_data = security.get_current_user(token)
    if not user_data:
        logger.warning(f"Invalid session token: {token[:10]}...")
        return None
    return user_data

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
    logger.info(f"Expense recorded: {description} - ₦{amount}")
    return True

def is_complaint_visible_to_user(complaint: dict, user_id: str) -> bool:
    """
    Check if a complaint is visible to a user based on hierarchy.
    A complaint is visible if:
    1. User is the tenant who created it
    2. User is the assignee (most important!)
    3. User is a Super Administrator or Administrator
    4. User is a Sub-Administrator and the assignee is their child (Agent or User they created)
    5. User is an Agent and the assignee is their parent (the Admin who created them)
    """
    assignee_id = complaint.get("assignee_id")
    tenant_id = complaint.get("tenant_id")
    
    # User can see complaints they created (as tenant)
    if tenant_id == user_id:
        return True
    
    # User can see complaints assigned to them - THIS IS THE MOST IMPORTANT CHECK
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
    
    # Sub-Administrator: can see complaints assigned to their children (Agents they created)
    if user_category == "Sub-Administrator":
        # Get all users created by this Sub-Admin (direct children)
        for u in users:
            if u.get("created_by") == user_id:
                # If this child is the assignee, the complaint is visible
                if u.get("user_id") == assignee_id:
                    return True
                # Also check if this child created the assignee (grandchildren)
                for u2 in users:
                    if u2.get("created_by") == u.get("user_id") and u2.get("user_id") == assignee_id:
                        return True
    
    # Agent: can see complaints assigned to their parent (Admin who created them)
    if user_category == "Agent":
        # Check if the assignee is the user's creator
        created_by = current_user.get("created_by")
        if created_by == assignee_id:
            return True
    
    # Check if user is the property creator (Administrator who owns the property)
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
        
        # Only tenants can make complaints
        if current_user.get("user_category") != "Tenant":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only tenants can create complaints"}
            )
        
        users = db.get_collection("users")
        properties = db.get_collection("properties")
        assignees = []
        
        # Get the tenant's assigned property to find the appropriate assignees
        assigned_property_id = current_user.get("assigned_property_id")
        property_creator = None
        
        if assigned_property_id:
            for p in properties:
                if p.get("_id") == assigned_property_id or p.get("id") == assigned_property_id:
                    property_creator = p.get("created_by")
                    break
        
        # Build a list of potential assignees
        for user in users:
            user_category = user.get("user_category", "")
            if user_category in ["Agent", "Sub-Administrator", "Administrator", "Super Administrator"]:
                # Check if this user is relevant to the tenant
                is_relevant = False
                
                # If the property creator is relevant
                if property_creator and user.get("user_id") == property_creator:
                    is_relevant = True
                
                # Super Admins and Admins are always relevant
                if user_category in ["Super Administrator", "Administrator"]:
                    is_relevant = True
                
                # Agents and Sub-Admins who created the property or are in the chain
                if not is_relevant and property_creator:
                    # Check if this user is under the property creator
                    if user.get("created_by") == property_creator:
                        is_relevant = True
                
                if is_relevant:
                    assignees.append({
                        "user_id": user.get("user_id"),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                        "user_category": user_category,
                        "email": user.get("email", "")
                    })
        
        # If no relevant assignees found, include all admins, sub-admins, and agents
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
# CREATE COMPLAINT (Tenant)
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
        
        # Only tenants can create complaints
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
        
        # Validate priority
        valid_priorities = ["low", "medium", "high", "emergency"]
        if priority not in valid_priorities:
            priority = "medium"
        
        # Get assignee info
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
        
        # Get the property ID from the tenant
        property_id = current_user.get("assigned_property_id")
        
        # Create complaint with "unattended" status
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
            "status": "unattended",  # unattended, contacted, in_progress, completed, resolved, not_resolved
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
            # Notify the assignee
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
            
            # Notify the tenant that complaint was submitted
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
        
        # Only tenants can view their complaints
        if current_user.get("user_category") != "Tenant":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Only tenants can view their complaints"}
            )
        
        complaints = db.get_collection("complaints")
        user_complaints = [c for c in complaints if c.get("tenant_id") == current_user.get("user_id")]
        
        # Sort by created_at descending
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
        
        # Check permissions
        user_id = current_user.get("user_id")
        user_category = current_user.get("user_category", "")
        
        # Super Admins can see all complaints
        if user_category == "Super Administrator":
            return JSONResponse({
                "success": True,
                "complaint": complaint
            })
        
        # Check if user has permission
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
        
        # Only these roles can view complaints
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
        
        # Apply status filter
        if status and status != "all":
            visible_complaints = [c for c in visible_complaints if c.get("status") == status]
            logger.info(f"After status filter '{status}': {len(visible_complaints)}")
        
        # Apply priority filter
        if priority and priority != "all":
            visible_complaints = [c for c in visible_complaints if c.get("priority") == priority]
            logger.info(f"After priority filter '{priority}': {len(visible_complaints)}")
        
        # Sort by priority (emergency first) and then by created_at
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
# UPDATE COMPLAINT (Admin/Agent) - FIXED
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
        
        # Only these roles can update complaints
        if user_category not in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        # Find the complaint
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
        
        # Check permission - user must be assignee, admin, or property creator
        assignee_id = complaint.get("assignee_id")
        property_id = complaint.get("property_id")
        
        can_update = False
        
        # User is the assignee
        if user_id == assignee_id:
            can_update = True
        
        # User is Super Admin
        if user_category == "Super Administrator":
            can_update = True
        
        # User is the property creator (Administrator)
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
        
        # Validate status
        valid_statuses = ["unattended", "contacted", "in_progress", "completed"]
        if new_status and new_status not in valid_statuses:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}
            )
        
        # Update fields
        old_status = complaint.get("status")
        
        if new_status:
            complaint["status"] = new_status
            
            # Reset escalation when status changes from unattended
            if new_status != "unattended":
                complaint["escalated"] = False
                complaint["escalation_level"] = 0
        
        if cost is not None:
            complaint["cost"] = float(cost)
        
        if admin_comment is not None:
            complaint["admin_comment"] = admin_comment
        
        complaint["updated_at"] = datetime.now().isoformat()
        
        # Save to database
        data = db.get_data()
        data["complaints"][complaint_index] = complaint
        success = db.update_data(data)
        
        if success:
            # Notify the tenant about status change
            tenant_id = complaint.get("tenant_id")
            if tenant_id:
                status_labels = {
                    "unattended": "Unattended",
                    "contacted": "Contacted Tenant",
                    "in_progress": "In Progress",
                    "completed": "Completed - Awaiting Your Confirmation"
                }
                status_label = status_labels.get(complaint.get("status"), complaint.get("status"))
                
                # If status is completed, send special notification asking for confirmation
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
            
            # If cost > 0 and status is completed, record as expense
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
# CONFIRM RESOLUTION (Tenant) - FIXED
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
        
        # Only tenants can confirm resolution
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
        
        # Find the complaint
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
        
        # Check if this complaint belongs to the tenant
        if complaint.get("tenant_id") != current_user.get("user_id"):
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "You can only confirm resolution for your own complaints"}
            )
        
        # Check if complaint is in completed status
        if complaint.get("status") != "completed":
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Complaint must be in 'completed' status before confirming resolution"}
            )
        
        # Update complaint
        complaint["resolved"] = resolved
        if resolved:
            complaint["status"] = "resolved"
        else:
            complaint["status"] = "not_resolved"
        complaint["updated_at"] = datetime.now().isoformat()
        
        # Save to database
        data = db.get_data()
        data["complaints"][complaint_index] = complaint
        success = db.update_data(data)
        
        if success:
            # Notify the assignee
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
            
            # If resolved, also notify the administrator
            if resolved:
                # Find the property creator
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
# GET COMPLAINT STATS
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
    
@router.get("/debug/check_assignee/{complaint_id}")
async def debug_check_assignee(request: Request, complaint_id: str):
    """Debug endpoint to check complaint assignee"""
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
        
        # Get all users for reference
        users = db.get_collection("users")
        user_map = {}
        for u in users:
            user_map[u.get("user_id")] = {
                "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("user_id"),
                "category": u.get("user_category", "Unknown")
            }
        
        return JSONResponse({
            "success": True,
            "complaint": {
                "id": complaint.get("_id"),
                "subject": complaint.get("subject"),
                "assignee_id": complaint.get("assignee_id"),
                "assignee_name": complaint.get("assignee_name"),
                "tenant_id": complaint.get("tenant_id"),
                "tenant_name": complaint.get("tenant_name"),
                "status": complaint.get("status"),
                "created_at": complaint.get("created_at")
            },
            "assignee_info": user_map.get(complaint.get("assignee_id"), {}),
            "tenant_info": user_map.get(complaint.get("tenant_id"), {}),
            "current_user": {
                "id": current_user.get("user_id"),
                "category": current_user.get("user_category")
            }
        })
        
    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )    