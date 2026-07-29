from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_agents():
    return {"message": "Get agents endpoint"}

@router.post("/")
async def create_agent():
    return {"message": "Create agent endpoint"}