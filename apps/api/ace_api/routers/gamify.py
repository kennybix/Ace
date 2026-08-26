from fastapi import APIRouter, Depends

from ace_api.engine import gamify as g
from ace_api.security import current_user

router = APIRouter(prefix="/me", tags=["gamify"])


@router.get("/gamify")
async def my_gamify(user=Depends(current_user)):
    return await g.summary(user["id"])
