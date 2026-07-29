from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class RentalProperty(BaseModel):
    _id: Optional[str] = None
    name: str
    description: str
    building_id: str
    building_name: str
    building_address: str
    building_state: str
    price: float
    visibility: str = "local"  # local or public
    photos: List[str] = []
    available: bool = True
    occupied_by: Optional[str] = None
    created_by: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

class PropertyCreate(BaseModel):
    name: str
    description: str
    building_id: str
    price: float
    visibility: str = "local"