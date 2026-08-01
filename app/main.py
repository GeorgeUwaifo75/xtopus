from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import os
from pathlib import Path
import logging


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the base directory
BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Import routers
from routers import (
    auth, users, agents, agreements, buildings, 
    chat, complaints, payments, properties, tenants, admin
)

# Import database
from database import db

# Create FastAPI app
app = FastAPI(title="Xtopus Property Management API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
else:
    logger.warning(f"Static directory not found: {STATIC_DIR}")

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(agreements.router, prefix="/api/agreements", tags=["Agreements"])
app.include_router(buildings.router, prefix="/api/buildings", tags=["Buildings"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(complaints.router, prefix="/api/complaints", tags=["Complaints"])
app.include_router(payments.router, prefix="/api/payments", tags=["Payments"])
app.include_router(properties.router, prefix="/api/properties", tags=["Properties"])
app.include_router(tenants.router, prefix="/api/tenants", tags=["Tenants"])

# Page routes
# Update the home() function in main.py

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - Only show available properties"""
    try:
        # Get all properties
        all_properties = db.get_collection("properties")
        # Filter only available properties
        available_properties = [p for p in all_properties if p.get("available", True)]
        # Limit to 12 properties for display
        properties = available_properties[:12]
        logger.info(f"Showing {len(properties)} available properties out of {len(all_properties)} total")
    except Exception as e:
        logger.error(f"Error fetching properties: {e}")
        properties = []
    
    # Get session token for template
    session_token = request.cookies.get("session_token")
    
    # Get user data if logged in
    user = None
    if session_token:
        from security import security
        user_data = security.get_current_user(session_token)
        if user_data:
            # Get full user data from database
            users = db.get_collection("users")
            for u in users:
                if u.get("user_id") == user_data.get("user_id"):
                    user = u
                    break
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "properties": properties,
        "mission": "Managing properties can be refreshing and relaxing again.",
        "session_token": session_token,
        "user": user  # <-- Add this line
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    # Check if already logged in
    token = request.cookies.get("session_token")
    if token:
        from security import security
        user = security.get_current_user(token)
        if user:
            return RedirectResponse(url="/dashboard", status_code=303)
    
    # Get messages from query params
    success = request.query_params.get("success", "")
    error = request.query_params.get("error", "")
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "success": success,
        "error": error
    })

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    """Signup page"""
    token = request.cookies.get("session_token")
    if token:
        from security import security
        user = security.get_current_user(token)
        if user:
            return RedirectResponse(url="/dashboard", status_code=303)
    
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard page - redirects based on user role"""
    token = request.cookies.get("session_token")
    if not token:
        return RedirectResponse(url="/login", status_code=303)
    
    from security import security
    user_data = security.get_current_user(token)
    if not user_data:
        return RedirectResponse(url="/login", status_code=303)
    
    # Get full user data
    users = db.get_collection("users")
    user = None
    for u in users:
        if u.get("user_id") == user_data.get("user_id"):
            user = u
            break
    
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    user_category = user.get("user_category", "Tenant")
    
    # Get data for dashboard
    buildings = db.get_collection("buildings")
    all_properties = db.get_collection("properties")
    # Filter only available properties for display
    available_properties = [p for p in all_properties if p.get("available", True)]
    tenants = db.get_collection("users")
    complaints = db.get_collection("complaints")
    payments = db.get_collection("payments")
    chats = db.get_collection("chats")
    
    # Check for pending tenant requests (for admins)
    pending_tenants = []
    if user_category in ["Super Administrator", "Administrator"]:
        for u in tenants:
            if u.get("user_category") == "Tenant" and u.get("tenant_status") == "pending":
                pending_tenants.append(u)
    
    # Get notifications for the user
    notifications_data = db.get_data()
    notifications = notifications_data.get("notifications", [])
    user_notifications = [n for n in notifications if n.get("user_id") == user.get("user_id") and not n.get("read", False)]
    user_notifications = user_notifications[-5:]  # Get the 5 most recent
    
    # Filter data based on user role
    if user_category == "Super Administrator":
        dashboard_template = "admin.html"
        context = {
            "request": request,
            "user": user,
            "buildings": buildings,
            "properties": all_properties,
            "tenants": [t for t in tenants if t.get("user_category") == "Tenant" and t.get("tenant_status") == "active"],
            "pending_tenants": pending_tenants,
            "pending_payments": [p for p in payments if p.get("status") == "pending"],
            "escalated_complaints": [c for c in complaints if c.get("status") == "escalated"],
            "pending_chats": len([c for c in chats if not c.get("read", False)]),
            "user_email": user.get("email"),
            "session_token": token,
            "notifications": user_notifications,
            "admins": [u for u in tenants if u.get("user_category") == "Administrator"],
            "agents": [u for u in tenants if u.get("user_category") == "Agent"],
            "sub_admins": [u for u in tenants if u.get("user_category") == "Sub-Administrator"]
        }
    elif user_category == "Administrator":
        user_id = user.get("user_id")
        admin_buildings = [b for b in buildings if b.get("created_by") == user_id]
        building_ids = [b.get("_id") for b in admin_buildings]
        admin_properties = [p for p in all_properties if p.get("building_id") in building_ids]
        
        dashboard_template = "admin.html"
        context = {
            "request": request,
            "user": user,
            "buildings": admin_buildings,
            "properties": admin_properties,
            "tenants": [t for t in tenants if t.get("user_category") == "Tenant" and t.get("tenant_status") == "active"],
            "pending_tenants": pending_tenants,
            "user_email": user.get("email"),
            "session_token": token,
            "notifications": user_notifications
        }
    # In the dashboard function, update the Sub-Administrator section:
    # In the dashboard function, update the Sub-Administrator section:
    elif user_category == "Sub-Administrator":
        # Get permissions for this sub-admin
        permissions = user.get("permissions", {})
        can_create_agents = permissions.get("can_create_agents", False)
        can_create_buildings = permissions.get("can_create_buildings", False)
        can_create_properties = permissions.get("can_create_properties", False)
        can_manage_tenants = permissions.get("can_manage_tenants", True)
        
        # Also check if the sub-admin can assign tenants
        can_assign_tenant = True  # Sub-admins can always assign tenants
        
        # Get all available properties for display
        available_properties = [p for p in all_properties if p.get("available", True)]
        
        dashboard_template = "dashboard.html"
        context = {
            "request": request,
            "user": user,
            "properties": all_properties,
            "all_properties": available_properties,  # Use available properties for display
            "user_email": user.get("email"),
            "session_token": token,
            "notifications": user_notifications,
            "can_assign_tenant": can_assign_tenant,
            # Add permissions to context
            "permissions": {
                "can_create_agents": can_create_agents,
                "can_create_buildings": can_create_buildings,
                "can_create_properties": can_create_properties,
                "can_manage_tenants": can_manage_tenants
            }
        }  

# In the dashboard function, make sure all_properties is passed to all user types
# Update the context for each user role to include all_properties with pagination

# For Agent:
    elif user_category == "Agent":
        user_id = user.get("user_id")
        agent_properties = [p for p in all_properties if p.get("created_by") == user_id]
        
        dashboard_template = "dashboard.html"
        context = {
            "request": request,
            "user": user,
            "properties": agent_properties,
            "all_properties": available_properties,  # Add this
            "user_email": user.get("email"),
            "session_token": token,
            "notifications": user_notifications,
            "can_assign_tenant": True
        }
    
    else:  # Tenant or regular user
        user_id = user.get("user_id")
        tenant_properties = [p for p in all_properties if p.get("occupied_by") == user_id]
        
        # Check if user is a pending tenant
        is_pending_tenant = user.get("tenant_status") == "pending"
        
        # ----- FIX: Define assigned_property_name -----
        assigned_property_name = user.get("assigned_property_name", "")
        if not assigned_property_name and user.get("assigned_property_id"):
            # Try to get property name from properties list
            for p in all_properties:
                if p.get("_id") == user.get("assigned_property_id") or p.get("id") == user.get("assigned_property_id"):
                    assigned_property_name = p.get("name", "")
                    break
        # ----------------------------------------------
        
        dashboard_template = "dashboard.html"
        context = {
            "request": request,
            "user": user,
            "properties": tenant_properties,
            "user_email": user.get("email"),
            "session_token": token,
            "notifications": user_notifications,
            "is_pending_tenant": is_pending_tenant,
            "all_properties": available_properties[:10],
            "assigned_property_name": assigned_property_name  # Now defined
        }
    
    return templates.TemplateResponse(dashboard_template, context)

@app.get("/logout")
async def logout():
    """Logout and redirect to home"""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session_token", path="/")
    return response

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        data = db.get_data()
        return {
            "status": "healthy",
            "users": len(data.get("users", [])),
            "buildings": len(data.get("buildings", [])),
            "properties": len(data.get("properties", []))
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

# Run the app
# if __name__ == "__main__":
#     import uvicorn
#     port = int(os.environ.get("PORT", 8000))
#     host = os.environ.get("HOST", "0.0.0.0")
#     logger.info(f"Starting Xtopus server at http://{host}:{port}")
#     uvicorn.run(app, host=host, port=port)
    
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    # For production, use these settings
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=2,  # Number of worker processes
        log_level="info"
    )