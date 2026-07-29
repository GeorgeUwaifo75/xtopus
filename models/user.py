from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any  # Added Dict and Any
from datetime import datetime
from enum import Enum

class UserCategory(str, Enum):
    SUPER_ADMIN = "Super Administrator"
    ADMINISTRATOR = "Administrator"
    SUB_ADMINISTRATOR = "Sub-Administrator"
    AGENT = "Agent"
    TENANT = "Tenant"

class User(BaseModel):
    _id: Optional[str] = None
    user_id: str
    username: str
    email: EmailStr
    password: str
    profile_photo: Optional[str] = None
    user_category: UserCategory
    activity_status: str = "Active"
    payment_status: str = "free"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # For Super Admin specific
    backup_data: Optional[Dict[str, Any]] = None
    
    @validator('user_id')
    def validate_user_id(cls, v):
        if len(v) < 3:
            raise ValueError('User ID must be at least 3 characters')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    password_confirm: str
    user_category: UserCategory
    user_id: str
    
    @validator('password_confirm')
    def passwords_match(cls, v, values):
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v

class UserLogin(BaseModel):
    user_id: str
    password: str

class UserResponse(BaseModel):
    _id: str
    user_id: str
    username: str
    email: str
    profile_photo: Optional[str]
    user_category: str
    activity_status: str
    payment_status: str
    
    class Config:
        orm_mode = True