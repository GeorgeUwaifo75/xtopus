from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_tenants():
    return {"message": "Get tenants endpoint"}

@router.post("/")
async def create_tenant():
    return {"message": "Create tenant endpoint"}