from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_buildings():
    return {"message": "Get buildings endpoint"}

@router.post("/")
async def create_building():
    return {"message": "Create building endpoint"}