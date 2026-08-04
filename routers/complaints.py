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
    """Background task to check for complaints that need escalation"""
    while True:
        try:
            time.sleep(60)  # Check every minute
            logger.info("Checking for complaints that need escalation...")
            
            complaints = db.get_collection("complaints")
            current_time = datetime.now()
            
            for complaint in complaints:
                # Check if complaint needs escalation
                if complaint.get("status") in ["pending", "in_progress"]:
                    created_at = complaint.get("created_at")
                    if created_at:
                        try:
                            created_dt = datetime.fromisoformat(created_at)
                            time_diff = current_time - created_dt
                            
                            # Check if 6 hours have passed
                            if time_diff >= timedelta(hours=6):
                                # Check if already escalated
                                if not complaint.get("escalated"):
                                    # Get current escalation level
                                    escalation_level = complaint.get("escalation_level", 0)
                                    max_level = 3  # Agent(0) -> Sub-Admin(1) -> Admin(2) -> Super Admin(3)
                                    
                                    # Determine current assignee level
                                    assignee_id = complaint.get("assignee_id")
                                    users = db.get_collection("users")
                                    assignee = None
                                    for u in users:
                                        if u.get("user_id") == assignee_id:
                                            assignee = u
                                            break
                                    
                                    if assignee:
                                        assignee_category = assignee.get("user_category", "")
                                        current_level = 0
                                        if assignee_category == "Agent":
                                            current_level = 0
                                        elif assignee_category == "Sub-Administrator":
                                            current_level = 1
                                        elif assignee_category == "Administrator":
                                            current_level = 2
                                        elif assignee_category == "Super Administrator":
                                            current_level = 3
                                        
                                        # Check if we can escalate further
                                        if current_level < 3:
                                            # Find next level user (Sub-Admin, Admin, or Super Admin)
                                            next_level_roles = {
                                                0: ["Sub-Administrator", "Administrator", "Super Administrator"],
                                                1: ["Administrator", "Super Administrator"],
                                                2: ["Super Administrator"],
                                                3: []
                                            }
                                            
                                            next_roles = next_level_roles.get(current_level, [])
                                            for role in next_roles:
                                                # Find the appropriate user with this role
                                                # For agents, find their parent Sub-Admin or Admin
                                                for u in users:
                                                    if u.get("user_category") == role:
                                                        # Check if this user is above the current assignee
                                                        # For Agent -> Sub-Admin, check if the Sub-Admin created the Agent
                                                        # For Sub-Admin -> Admin, check if the Admin created the Sub-Admin
                                                        if current_level == 0:  # Agent -> Sub-Admin/Admin
                                                            # Check if this user created the agent
                                                            if u.get("user_id") == assignee.get("created_by"):
                                                                # Escalate to this user
                                                                new_assignee = u.get("user_id")
                                                                new_assignee_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("user_id")
                                                                
                                                                # Update complaint
                                                                complaint["assignee_id"] = new_assignee
                                                                complaint["assignee_name"] = new_assignee_name
                                                                complaint["escalated"] = True
                                                                complaint["escalation_level"] = current_level + 1
                                                                complaint["escalated_at"] = datetime.now().isoformat()
                                                                complaint["updated_at"] = datetime.now().isoformat()
                                                                
                                                                # Add escalation message
                                                                if "escalation_history" not in complaint:
                                                                    complaint["escalation_history"] = []
                                                                complaint["escalation_history"].append({
                                                                    "from": assignee_id,
                                                                    "to": new_assignee,
                                                                    "reason": f"Auto-escalated after 6 hours of no response",
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
                                                                    new_assignee,
                                                                    "complaint_escalated",
                                                                    f"⚠️ Complaint '{complaint.get('subject')}' has been escalated to you after 6 hours of no response.",
                                                                    {
                                                                        "complaint_id": complaint.get("_id"),
                                                                        "subject": complaint.get("subject"),
                                                                        "tenant_id": complaint.get("tenant_id")
                                                                    }
                                                                )
                                                                
                                                                logger.info(f"Complaint {complaint.get('_id')} escalated from {assignee_id} to {new_assignee}")
                                                                break
                                                        elif current_level == 1:  # Sub-Admin -> Admin
                                                            if u.get("user_id") == assignee.get("created_by"):
                                                                # Escalate to this user
                                                                new_assignee = u.get("user_id")
                                                                new_assignee_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("user_id")
                                                                
                                                                # Update complaint
                                                                complaint["assignee_id"] = new_assignee
                                                                complaint["assignee_name"] = new_assignee_name
                                                                complaint["escalated"] = True
                                                                complaint["escalation_level"] = current_level + 1
                                                                complaint["escalated_at"] = datetime.now().isoformat()
                                                                complaint["updated_at"] = datetime.now().isoformat()
                                                                
                                                                # Add escalation message
                                                                if "escalation_history" not in complaint:
                                                                    complaint["escalation_history"] = []
                                                                complaint["escalation_history"].append({
                                                                    "from": assignee_id,
                                                                    "to": new_assignee,
                                                                    "reason": f"Auto-escalated after 6 hours of no response",
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
                                                                    new_assignee,
                                                                    "complaint_escalated",
                                                                    f"⚠️ Complaint '{complaint.get('subject')}' has been escalated to you after 6 hours of no response.",
                                                                    {
                                                                        "complaint_id": complaint.get("_id"),
                                                                        "subject": complaint.get("subject"),
                                                                        "tenant_id": complaint.get("tenant_id")
                                                                    }
                                                                )
                                                                
                                                                logger.info(f"Complaint {complaint.get('_id')} escalated from {assignee_id} to {new_assignee}")
                                                                break
                                                        elif current_level == 2:  # Admin -> Super Admin
                                                            if u.get("user_category") == "Super Administrator":
                                                                new_assignee = u.get("user_id")
                                                                new_assignee_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("user_id")
                                                                
                                                                # Update complaint
                                                                complaint["assignee_id"] = new_assignee
                                                                complaint["assignee_name"] = new_assignee_name
                                                                complaint["escalated"] = True
                                                                complaint["escalation_level"] = current_level + 1
                                                                complaint["escalated_at"] = datetime.now().isoformat()
                                                                complaint["updated_at"] = datetime.now().isoformat()
                                                                
                                                                # Add escalation message
                                                                if "escalation_history" not in complaint:
                                                                    complaint["escalation_history"] = []
                                                                complaint["escalation_history"].append({
                                                                    "from": assignee_id,
                                                                    "to": new_assignee,
                                                                    "reason": f"Auto-escalated after 6 hours of no response",
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
                                                                    new_assignee,
                                                                    "complaint_escalated",
                                                                    f"⚠️ Complaint '{complaint.get('subject')}' has been escalated to you after 6 hours of no response.",
                                                                    {
                                                                        "complaint_id": complaint.get("_id"),
                                                                        "subject": complaint.get("subject"),
                                                                        "tenant_id": complaint.get("tenant_id")
                                                                    }
                                                                )
                                                                
                                                                logger.info(f"Complaint {complaint.get('_id')} escalated from {assignee_id} to {new_assignee}")
                                                                break
                                            break
                                        else:
                                            # Already at highest level, mark as escalated
                                            complaint["escalated"] = True
                                            complaint["escalation_level"] = 3
                                            complaint["updated_at"] = datetime.now().isoformat()
                                            
                                            data = db.get_data()
                                            for idx, c in enumerate(data.get("complaints", [])):
                                                if c.get("_id") == complaint.get("_id"):
                                                    data["complaints"][idx] = complaint
                                                    db.update_data(data)
                                                    break
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

def get_user_hierarchy(current_user_id: str) -> dict:
    """
    Get the hierarchy relationships for a user.
    Returns a dict with:
    - user_id: the current user
    - user_category: the user's role
    - created_by: who created this user (if any)
    - created_users: list of users this user created
    - children: list of user IDs under this user (direct and indirect)
    - parent: the user who created this user (if any)
    """
    users = db.get_collection("users")
    
    # Find the current user
    current_user = None
    for u in users:
        if u.get("user_id") == current_user_id:
            current_user = u
            break
    
    if not current_user:
        return {"error": "User not found"}
    
    user_category = current_user.get("user_category", "User")
    created_by = current_user.get("created_by")
    
    # Find all users created by this user (direct children)
    created_users = []
    for u in users:
        if u.get("created_by") == current_user_id:
            created_users.append(u.get("user_id"))
    
    # Find the parent user (who created this user)
    parent_user = None
    if created_by:
        for u in users:
            if u.get("user_id") == created_by:
                parent_user = u
                break
    
    # Get all users under this user (children, grandchildren, etc.)
    def get_all_descendants(user_id):
        descendants = []
        for u in users:
            if u.get("created_by") == user_id:
                descendants.append(u.get("user_id"))
                # Recursively get their children
                descendants.extend(get_all_descendants(u.get("user_id")))
        return descendants
    
    all_descendants = get_all_descendants(current_user_id)
    
    return {
        "user_id": current_user_id,
        "user_category": user_category,
        "created_by": created_by,
        "parent": parent_user,
        "created_users": created_users,
        "all_descendants": all_descendants,
        "is_admin": user_category in ["Super Administrator", "Administrator"],
        "is_sub_admin": user_category == "Sub-Administrator",
        "is_agent": user_category == "Agent"
    }

# In complaints.py, replace the is_complaint_visible_to_user function with this:

def is_complaint_visible_to_user(complaint: dict, user_id: str, user_hierarchy: dict = None) -> bool:
    """
    Check if a complaint is visible to a user based on hierarchy.
    A complaint is visible if:
    1. The user is the assignee
    2. The user is a Super Admin or Admin (can see all)
    3. The user is the parent/creator of the assignee (can see complaints assigned to their children)
    4. The user is a child of the assignee (can see complaints assigned to their parent)
    5. The user is the tenant who created the complaint
    """
    if user_hierarchy is None:
        user_hierarchy = get_user_hierarchy(user_id)
    
    if "error" in user_hierarchy:
        return False
    
    assignee_id = complaint.get("assignee_id")
    tenant_id = complaint.get("tenant_id")
    user_category = user_hierarchy.get("user_category", "User")
    
    # Super Administrators and Administrators can see all complaints
    if user_category in ["Super Administrator", "Administrator"]:
        logger.info(f"Admin {user_id} can see all complaints")
        return True
    
    # User can see complaints they created (as tenant)
    if tenant_id == user_id:
        logger.info(f"Tenant {user_id} can see their own complaint")
        return True
    
    # User can see complaints assigned to them
    if assignee_id == user_id:
        logger.info(f"User {user_id} is the assignee")
        return True
    
    # Sub-Admin can see complaints assigned to their agents (children)
    if user_category == "Sub-Administrator":
        # Check if the assignee is a descendant (created by this sub-admin or their agents)
        all_descendants = user_hierarchy.get("all_descendants", [])
        if assignee_id in all_descendants:
            logger.info(f"Sub-Admin {user_id} can see complaint assigned to their agent {assignee_id}")
            return True
        
        # Also check if the assignee is the sub-admin themselves (they are the assignee)
        # This is already covered by the assignee_id == user_id check above
    
    # Agent can see complaints assigned to them (already covered above)
    # Agents can also see complaints assigned to their parent (the sub-admin/admin who created them)
    if user_category == "Agent":
        # Check if the assignee is the parent of this agent
        parent_user = user_hierarchy.get("parent")
        if parent_user and parent_user.get("user_id") == assignee_id:
            logger.info(f"Agent {user_id} can see complaint assigned to their parent {assignee_id}")
            return True
        
        # Also, if the complaint is assigned to this agent's parent, they should see it
        # This helps agents see complaints that were escalated to their admin
    
    # If the user is a Sub-Administrator, they can also see complaints assigned to them
    # This is already covered by assignee_id == user_id
    
    return False

# ============================================
# GET ASSIGNEES FOR COMPLAINT DROPDOWN
# ============================================
@router.get("/get_assignees")
async def get_assignees(request: Request):
    """Get list of users who can be assigned complaints (Agents, Admins, Sub-Admins)"""
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
        assignees = []
        
        # Get the user who assigned this tenant (agent/sub-admin/admin)
        assigned_by = current_user.get("tenant_assigned_by")
        
        # Get the tenant's assigned property to find the appropriate assignees
        assigned_property_id = current_user.get("assigned_property_id")
        property_creator = None
        
        if assigned_property_id:
            properties = db.get_collection("properties")
            for p in properties:
                if p.get("_id") == assigned_property_id or p.get("id") == assigned_property_id:
                    property_creator = p.get("created_by")
                    break
        
        # Build a list of potential assignees
        # Order of authority: Agent (lowest) -> Sub-Administrator -> Administrator -> Super Administrator (highest)
        for user in users:
            user_category = user.get("user_category", "")
            if user_category in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
                # Check if this user is relevant to the tenant
                is_relevant = False
                
                # If the tenant was assigned by someone, that person should be an option
                if assigned_by and user.get("user_id") == assigned_by:
                    is_relevant = True
                
                # If the property creator is relevant
                if property_creator and user.get("user_id") == property_creator:
                    is_relevant = True
                
                # Super Admins and Admins are always relevant
                if user_category in ["Super Administrator", "Administrator"]:
                    is_relevant = True
                
                if is_relevant:
                    assignees.append({
                        "user_id": user.get("user_id"),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                        "user_category": user_category,
                        "email": user.get("email", ""),
                        "priority": 0 if user.get("user_id") == assigned_by else (
                            1 if user_category == "Agent" else (
                                2 if user_category == "Sub-Administrator" else (
                                    3 if user_category == "Administrator" else 4
                                )
                            )
                        )
                    })
        
        # If no relevant assignees found, include all admins and agents
        if not assignees:
            for user in users:
                user_category = user.get("user_category", "")
                if user_category in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
                    assignees.append({
                        "user_id": user.get("user_id"),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                        "user_category": user_category,
                        "email": user.get("email", ""),
                        "priority": 0 if user.get("user_id") == assigned_by else (
                            1 if user_category == "Agent" else (
                                2 if user_category == "Sub-Administrator" else (
                                    3 if user_category == "Administrator" else 4
                                )
                            )
                        )
                    })
        
        # Sort by priority (assigned_by first, then Agent, Sub-Admin, Admin, Super Admin)
        assignees.sort(key=lambda x: x.get("priority", 5))
        
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
        
        # Create complaint
        complaint = {
            "_id": f"comp_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}",
            "tenant_id": current_user.get("user_id"),
            "tenant_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get("user_id"),
            "assignee_id": assignee_id,
            "assignee_name": f"{assignee.get('first_name', '')} {assignee.get('last_name', '')}".strip() or assignee_id,
            "subject": subject,
            "description": description,
            "priority": priority,
            "status": "pending",  # pending, in_progress, completed, resolved, not_resolved
            "cost": 0,
            "admin_comment": "",
            "resolved": None,  # True, False, or None (not yet confirmed)
            "escalated": False,
            "escalation_level": 0,
            "escalated_at": None,
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
            
            # Also notify higher-level admins (if the assignee is not an admin)
            assignee_category = assignee.get("user_category", "")
            if assignee_category not in ["Super Administrator", "Administrator"]:
                for u in users:
                    if u.get("user_category") in ["Super Administrator", "Administrator"]:
                        # Check if this admin is above the assignee in the hierarchy
                        if assignee_category == "Agent":
                            # Check if this admin created the agent's parent
                            created_by = assignee.get("created_by")
                            if created_by:
                                parent_user = None
                                for p in users:
                                    if p.get("user_id") == created_by:
                                        parent_user = p
                                        break
                                if parent_user and parent_user.get("user_category") == u.get("user_category"):
                                    create_notification(
                                        u.get("user_id"),
                                        "complaint_notification",
                                        f"📋 New complaint from {complaint['tenant_name']} assigned to {complaint['assignee_name']}: {subject}",
                                        {
                                            "complaint_id": complaint["_id"],
                                            "subject": subject,
                                            "tenant_id": current_user.get("user_id"),
                                            "assignee_id": assignee_id
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
        
        # Check permissions using hierarchy
        user_id = current_user.get("user_id")
        user_hierarchy = get_user_hierarchy(user_id)
        
        if "error" in user_hierarchy:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        if not is_complaint_visible_to_user(complaint, user_id, user_hierarchy):
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

# In complaints.py, update the get_assigned_complaints function:

@router.get("/assigned")
async def get_assigned_complaints(
    request: Request,
    status: Optional[str] = None,
    priority: Optional[str] = None
):
    """Get complaints visible to the current user based on hierarchy"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        user_id = current_user.get("user_id")
        user_hierarchy = get_user_hierarchy(user_id)
        
        if "error" in user_hierarchy:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to get user hierarchy"}
            )
        
        all_complaints = db.get_collection("complaints")
        visible_complaints = []
        
        logger.info(f"Checking visibility for user {user_id} ({user_category})")
        logger.info(f"Total complaints: {len(all_complaints)}")
        logger.info(f"User hierarchy: created_by={user_hierarchy.get('created_by')}, descendants={user_hierarchy.get('all_descendants', [])}")
        
        for complaint in all_complaints:
            assignee_id = complaint.get("assignee_id")
            tenant_id = complaint.get("tenant_id")
            
            # Log each complaint for debugging
            logger.info(f"Complaint: {complaint.get('_id')} - assignee={assignee_id}, tenant={tenant_id}, status={complaint.get('status')}")
            
            # For Agents: they should see complaints where they are the assignee
            if user_category == "Agent" and assignee_id == user_id:
                visible_complaints.append(complaint)
                logger.info(f"Agent {user_id} is assignee for complaint {complaint.get('_id')}")
                continue
            
            # For Sub-Administrators: they should see complaints where they are the assignee
            # or where their agents are the assignee
            if user_category == "Sub-Administrator":
                if assignee_id == user_id:
                    visible_complaints.append(complaint)
                    logger.info(f"Sub-Admin {user_id} is assignee for complaint {complaint.get('_id')}")
                    continue
                if assignee_id in user_hierarchy.get("all_descendants", []):
                    visible_complaints.append(complaint)
                    logger.info(f"Sub-Admin {user_id} can see complaint assigned to agent {assignee_id}")
                    continue
            
            # Use the enhanced visibility function for other cases
            if is_complaint_visible_to_user(complaint, user_id, user_hierarchy):
                visible_complaints.append(complaint)
                logger.info(f"Complaint {complaint.get('_id')} is visible to {user_id} via hierarchy")
        
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
        visible_complaints.sort(key=lambda x: (
            priority_order.get(x.get("priority", "medium"), 2),
            0 if x.get("status") in ["pending", "in_progress"] else 1,
            x.get("created_at", "")
        ), reverse=False)
        
        return JSONResponse({
            "success": True,
            "complaints": visible_complaints,
            "count": len(visible_complaints),
            "user_hierarchy": {
                "category": user_hierarchy.get("user_category"),
                "created_by": user_hierarchy.get("created_by"),
                "has_descendants": len(user_hierarchy.get("all_descendants", [])) > 0
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
        
        # Check permission using hierarchy
        user_id = current_user.get("user_id")
        user_hierarchy = get_user_hierarchy(user_id)
        
        if "error" in user_hierarchy:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        if not is_complaint_visible_to_user(complaint, user_id, user_hierarchy):
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "You don't have permission to update this complaint"}
            )
        
        # Check if user can update (must be assignee or above in hierarchy)
        assignee_id = complaint.get("assignee_id")
        if user_id != assignee_id and user_category not in ["Super Administrator", "Administrator"]:
            # Check if user is a parent of the assignee
            if assignee_id not in user_hierarchy.get("all_descendants", []):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "You can only update complaints assigned to you or your team"}
                )
        
        body = await request.json()
        new_status = body.get("status")
        cost = body.get("cost")
        admin_comment = body.get("admin_comment")
        
        # Validate status
        valid_statuses = ["pending", "in_progress", "completed"]
        if new_status and new_status not in valid_statuses:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}
            )
        
        # Update fields
        if new_status:
            complaint["status"] = new_status
            
            # If status is completed, reset resolved status
            if new_status == "completed":
                complaint["resolved"] = None  # Awaiting tenant confirmation
                # Reset escalation flag since complaint is completed
                complaint["escalated"] = False
        
        if cost is not None:
            complaint["cost"] = float(cost)
        
        if admin_comment is not None:
            complaint["admin_comment"] = admin_comment
        
        # Reset escalation timer when status changes
        if new_status and new_status in ["in_progress", "completed"]:
            complaint["escalated"] = False
            complaint["escalation_level"] = 0
        
        complaint["updated_at"] = datetime.now().isoformat()
        
        # Save to database
        data = db.get_data()
        data["complaints"][complaint_index] = complaint
        success = db.update_data(data)
        
        if success:
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
            
            # Notify the tenant about status change
            if complaint.get("tenant_id"):
                status_labels = {
                    "pending": "Pending",
                    "in_progress": "In Progress",
                    "completed": "Completed"
                }
                status_label = status_labels.get(complaint.get("status"), complaint.get("status"))
                
                message = f"📋 Your complaint '{complaint.get('subject')}' has been updated to: {status_label}"
                if admin_comment:
                    message += f"\n\nNote: {admin_comment}"
                if complaint.get("cost", 0) > 0:
                    message += f"\n\n💰 Cost: ₦{complaint.get('cost', 0)}"
                
                create_notification(
                    complaint.get("tenant_id"),
                    "complaint_updated",
                    message,
                    {
                        "complaint_id": complaint_id,
                        "status": complaint.get("status"),
                        "cost": complaint.get("cost", 0)
                    }
                )
            
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
# GET COMPLAINT STATS (Admin)
# ============================================
@router.get("/stats")
async def get_complaint_stats(request: Request):
    """Get complaint statistics for dashboard based on hierarchy"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        user_category = current_user.get("user_category", "")
        if user_category not in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        user_id = current_user.get("user_id")
        user_hierarchy = get_user_hierarchy(user_id)
        
        if "error" in user_hierarchy:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to get user hierarchy"}
            )
        
        all_complaints = db.get_collection("complaints")
        visible_complaints = []
        
        for complaint in all_complaints:
            if is_complaint_visible_to_user(complaint, user_id, user_hierarchy):
                visible_complaints.append(complaint)
        
        stats = {
            "total": len(visible_complaints),
            "pending": len([c for c in visible_complaints if c.get("status") == "pending"]),
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
# DEBUG ENDPOINT
# ============================================
@router.get("/debug/all")
async def debug_all_complaints(request: Request):
    """DEBUG: Get all complaints with assignee info"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Only super admin can access this
        if current_user.get("user_category") != "Super Administrator":
            return JSONResponse(
                status_code=403,
                content={"success": False, "detail": "Access denied"}
            )
        
        complaints = db.get_collection("complaints")
        
        # Add user info to each complaint
        users = db.get_collection("users")
        user_map = {}
        for u in users:
            user_map[u.get("user_id")] = {
                "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("user_id"),
                "category": u.get("user_category", "Unknown"),
                "created_by": u.get("created_by")
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

# ============================================
# START ESCALATION CHECKER ON APP STARTUP
# ============================================
# Note: In production, this should be started in main.py
# For now, we'll start it when the router is imported
start_escalation_checker()