from fastapi import APIRouter

from .oecd import router as oecd_router

# Currently the only router for economic data
router = APIRouter(prefix="/economic", tags=["economic"])

router.include_router(oecd_router, tags=["oecd"])

