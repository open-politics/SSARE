from fastapi import APIRouter

from .germany import router as germany_router
router = APIRouter(prefix="/legislation", tags=["legislation"])

router.include_router(germany_router, tags=["germany"])

