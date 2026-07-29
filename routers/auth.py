from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional
import json
from datetime import datetime
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Import models and database
from models.user import UserCreate, UserLogin, UserCategory
from database import db
from security import security

@router.post("/login")
async def login(request: Request):
    """Handle login form submission"""
    try:
        form = await request.form()
        user_id = form.get("user_id")
        password = form.get("password")
        
        if not user_id or not password:
            raise HTTPException(status_code=400, detail="User ID and password required")
        
        logger.info(f"Login attempt for user: {user_id}")
        
        # Get users from database
        users = db.get_collection("users")
        logger.info(f"Found {len(users)} users in database")
        
        # Find user by user_id (case-insensitive)
        user = None
        for u in users:
            if u.get("user_id", "").lower() == user_id.lower():
                user = u
                break
        
        if not user:
            logger.warning(f"User not found: {user_id}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password
        if not security.verify_password(password, user.get("password")):
            logger.warning(f"Invalid password for user: {user_id}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        logger.info(f"User authenticated: {user_id}")
        
        # Create access token
        token_data = {
            "sub": user.get("user_id"),
            "email": user.get("email"),
            "user_category": user.get("user_category", "User"),
            "username": user.get("username")
        }
        token = security.create_access_token(token_data)
        
        # Update last login
        db.update_collection_item("users", user.get("_id") or user.get("id"), {
            "last_login": datetime.now().isoformat()
        })
        
        # Create response
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            max_age=security.access_token_expire_minutes * 60,
            path="/",
            samesite="lax"
        )
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@router.post("/signup")
async def signup(request: Request):
    """Handle signup form submission"""
    try:
        form = await request.form()
        
        # Extract form data
        user_id = form.get("user_id")
        email = form.get("email")
        first_name = form.get("first_name")
        last_name = form.get("last_name")
        password = form.get("password")
        password_confirm = form.get("password_confirm")
        gender = form.get("gender")
        age = form.get("age")
        country = form.get("country")
        
        logger.info(f"Signup attempt for user: {user_id}")
        
        # Validate
        if not all([user_id, email, first_name, last_name, password, password_confirm]):
            raise HTTPException(status_code=400, detail="All fields are required")
        
        if password != password_confirm:
            raise HTTPException(status_code=400, detail="Passwords do not match")
        
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        
        # Check if user already exists
        users = db.get_collection("users")
        for u in users:
            if u.get("user_id", "").lower() == user_id.lower():
                raise HTTPException(status_code=400, detail="User ID already exists")
            if u.get("email", "").lower() == email.lower():
                raise HTTPException(status_code=400, detail="Email already registered")
        
        # Hash password
        hashed_password = security.hash_password(password)
        
        # Create user object - Set user_category to "User" (not Tenant)
        new_user = {
            "user_id": user_id,
            "email": email,
            "username": f"{first_name} {last_name}",
            "first_name": first_name,
            "last_name": last_name,
            "password": hashed_password,
            "gender": gender,
            "age": int(age) if age else None,
            "country": country,
            "user_category": "User",  # Changed from "Tenant" to "User"
            "activity_status": "Active",
            "payment_status": "free",
            "profile_photo": None,
            "tenant_status": None,  # Add tenant_status field
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # Save to database
        success = db.add_to_collection("users", new_user)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create account. Please try again.")
        
        logger.info(f"User created successfully: {user_id} with category: User")
        
        # Redirect to login
        response = RedirectResponse(url="/login?success=Account created successfully! Please login.", status_code=303)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status_code=500, detail=f"Signup failed: {str(e)}")

@router.post("/logout")
async def logout():
    """Handle logout"""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session_token", path="/")
    return response

@router.get("/check")
async def check_auth(request: Request):
    """Check if user is authenticated"""
    token = request.cookies.get("session_token")
    if not token:
        return JSONResponse({"authenticated": False})
    
    user = security.get_current_user(token)
    if not user:
        return JSONResponse({"authenticated": False})
    
    return JSONResponse({"authenticated": True, "user": user})