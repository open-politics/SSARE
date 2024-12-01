from fastapi import APIRouter
from .search.routes import router as search_router
from .pipelines.routes import router as pipeline_router
from .helper.routes import router as helper_router
from .dimensions.routes import router as dimensions_router

api_router = APIRouter()

api_router.include_router(search_router, tags=["search"])
api_router.include_router(pipeline_router, tags=["pipelines"])
api_router.include_router(helper_router, tags=["helper"])
api_router.include_router(dimensions_router, tags=["dimensions"])