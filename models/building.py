from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class State(str, Enum):
    ABIA = "Abia"
    ADAMAWA = "Adamawa"
    AKWA_IBOM = "Akwa Ibom"
    ANAMBRA = "Anambra"
    BAUCHI = "Bauchi"
    BAYELSA = "Bayelsa"
    BENUE = "Benue"
    BORNO = "Borno"
    CROSS_RIVER = "Cross River"
    DELTA = "Delta"
    EBONYI = "Ebonyi"
    EDO = "Edo"
    EKITI = "Ekiti"
    ENUGU = "Enugu"
    FCT = "FCT"
    GOMBE = "Gombe"
    IMO = "Imo"
    JIGAWA = "Jigawa"
    KADUNA = "Kaduna"
    KANO = "Kano"
    KATSINA = "Katsina"
    KEBBI = "Kebbi"
    KOGI = "Kogi"
    KWARA = "Kwara"
    LAGOS = "Lagos"
    NASARAWA = "Nasarawa"
    NIGER = "Niger"
    OGUN = "Ogun"
    ONDO = "Ondo"
    OSUN = "Osun"
    OYO = "Oyo"
    PLATEAU = "Plateau"
    RIVERS = "Rivers"
    SOKOTO = "Sokoto"
    TARABA = "Taraba"
    YOBE = "Yobe"
    ZAMFARA = "Zamfara"

class UnitType(str, Enum):
    ROOMS = "Rooms"
    APARTMENTS = "Apartments"
    FLATS = "Flats"
    BUNGALOW = "Bungalow"
    DUPLEX = "Duplex"
    OFFICE = "Office"
    OTHER = "Other"

class Category(str, Enum):
    WHOLE_RENTAL = "Whole rental"
    SUB_RENTAL = "Sub-rental"

class Building(BaseModel):
    _id: Optional[str] = None
    name: str
    description: str
    address: str
    state: State
    unit_type: UnitType
    number_of_units: int
    category: Category
    photos: List[str] = []
    created_by: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

class BuildingCreate(BaseModel):
    name: str
    description: str
    address: str
    state: State
    unit_type: UnitType
    number_of_units: int
    category: Category = Category.SUB_RENTAL