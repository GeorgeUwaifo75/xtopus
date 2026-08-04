from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime
import logging
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)

from database import db
from security import security

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
        
        for user in users:
            user_category = user.get("user_category", "")
            # Include Super Administrators, Administrators, Sub-Administrators, and Agents
            if user_category in ["Super Administrator", "Administrator", "Sub-Administrator", "Agent"]:
                assignees.append({
                    "user_id": user.get("user_id"),
                    "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("user_id"),
                    "user_category": user_category,
                    "email": user.get("email", "")
                })
        
        # Sort: put the assigned_by person first, then by category priority
        assignees.sort(key=lambda x: (
            0 if x.get("user_id") == assigned_by else 1,
            0 if x.get("user_category") == "Super Administrator" else 1,
            0 if x.get("user_category") == "Administrator" else 2,
            0 if x.get("user_category") == "Sub-Administrator" else 3,
            0 if x.get("user_category") == "Agent" else 4
        ))
        
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
        
        # Tenant can only view their own complaints
        if user_category == "Tenant":
            if complaint.get("tenant_id") != user_id:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "You can only view your own complaints"}
                )
        # Others can view if they are the assignee or an admin
        else:
            if complaint.get("assignee_id") != user_id and user_category not in ["Super Administrator", "Administrator"]:
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
# GET ASSIGNED COMPLAINTS (Admin/Agent) - FIXED
# ============================================
@router.get("/assigned")
async def get_assigned_complaints(
    request: Request,
    status: Optional[str] = None,
    priority: Optional[str] = None
):
    """Get complaints assigned to the current user (for admins and agents)"""
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
        
        complaints = db.get_collection("complaints")
        current_user_id = current_user.get("user_id")
        
        logger.info(f"Fetching complaints for user: {current_user_id}, role: {user_category}")
        logger.info(f"Total complaints in database: {len(complaints)}")
        
        # Filter by assignee
        if user_category in ["Super Administrator", "Administrator"]:
            # Admins can see all complaints
            assigned_complaints = complaints
            logger.info(f"Admin sees all {len(assigned_complaints)} complaints")
        else:
            # Agents and Sub-Admins can only see complaints assigned to them
            assigned_complaints = [c for c in complaints if c.get("assignee_id") == current_user_id]
            logger.info(f"Agent/SubAdmin sees {len(assigned_complaints)} complaints assigned to them")
            
            # Log complaints for debugging
            for c in complaints:
                logger.debug(f"Complaint {c.get('_id')}: assignee_id={c.get('assignee_id')}, subject={c.get('subject')}")
        
        # Apply status filter
        if status and status != "all":
            assigned_complaints = [c for c in assigned_complaints if c.get("status") == status]
            logger.info(f"After status filter '{status}': {len(assigned_complaints)} complaints")
        
        # Apply priority filter
        if priority and priority != "all":
            assigned_complaints = [c for c in assigned_complaints if c.get("priority") == priority]
            logger.info(f"After priority filter '{priority}': {len(assigned_complaints)} complaints")
        
        # Sort by priority (emergency first) and then by created_at
        priority_order = {"emergency": 0, "high": 1, "medium": 2, "low": 3}
        assigned_complaints.sort(key=lambda x: (
            priority_order.get(x.get("priority", "medium"), 2),
            0 if x.get("status") in ["pending", "in_progress"] else 1,
            x.get("created_at", "")
        ), reverse=False)
        
        return JSONResponse({
            "success": True,
            "complaints": assigned_complaints,
            "count": len(assigned_complaints)
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
        
        # Check permission - user must be the assignee or an admin
        if user_category not in ["Super Administrator", "Administrator"]:
            if complaint.get("assignee_id") != current_user.get("user_id"):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "You can only update complaints assigned to you"}
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
    """Get complaint statistics for dashboard"""
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
        
        complaints = db.get_collection("complaints")
        current_user_id = current_user.get("user_id")
        
        # Filter by assignee if not admin
        if user_category in ["Super Administrator", "Administrator"]:
            all_complaints = complaints
        else:
            all_complaints = [c for c in complaints if c.get("assignee_id") == current_user_id]
        
        stats = {
            "total": len(all_complaints),
            "pending": len([c for c in all_complaints if c.get("status") == "pending"]),
            "in_progress": len([c for c in all_complaints if c.get("status") == "in_progress"]),
            "completed": len([c for c in all_complaints if c.get("status") == "completed"]),
            "resolved": len([c for c in all_complaints if c.get("status") == "resolved"]),
            "not_resolved": len([c for c in all_complaints if c.get("status") == "not_resolved"])
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

# Add to complaints.py - DEBUG endpoint to check all complaints
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
                "status": c.get("status"),
                "priority": c.get("priority"),
                "created_at": c.get("created_at")
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