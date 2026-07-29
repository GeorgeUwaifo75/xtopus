from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_payments():
    return {"message": "Get payments endpoint"}

@router.post("/")
async def create_payment():
    return {"message": "Create payment endpoint"}