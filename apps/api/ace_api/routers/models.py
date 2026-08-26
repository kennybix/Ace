from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ace_api import db
from ace_api.config import settings
from ace_api.security import current_user

router = APIRouter(tags=["models"])


class ModelSelect(BaseModel):
    model_id: str


@router.get("/models")
async def list_models(user=Depends(current_user)):
    return {"models": [{"id": m["id"], "label": m["label"]} for m in settings().llm_models],
            "selected": user["selected_model"]}


@router.put("/me/model")
async def select_model(body: ModelSelect, user=Depends(current_user)):
    if body.model_id not in {m["id"] for m in settings().llm_models}:
        raise HTTPException(400, "unknown model")
    await db.execute("UPDATE users SET selected_model=%s WHERE id=%s", (body.model_id, user["id"]))
    return {"selected": body.model_id, "applies_to": "newly generated content only"}
