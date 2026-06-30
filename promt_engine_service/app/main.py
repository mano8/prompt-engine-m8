"""
Main routes
"""

from fastapi import APIRouter

from promt_engine_service.app.routes import category, dashboard, prompt_blocks, prompt_templates

api_router = APIRouter()
api_router.include_router(dashboard.router)
api_router.include_router(category.router)
api_router.include_router(prompt_blocks.router)
api_router.include_router(prompt_templates.router)