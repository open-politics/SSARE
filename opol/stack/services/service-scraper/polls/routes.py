from fastapi import APIRouter
from .germany import router as germany_router

router = APIRouter(prefix="/polls", tags=["polls"])

router.include_router(germany_router, tags=["polls"])
