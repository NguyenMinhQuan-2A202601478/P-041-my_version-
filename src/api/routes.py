"""Router chinh cua API v1 — gom tat ca sub-router (auth, cvs, jds, ...) lai.

`src/main.py` chi can `include_router(api_router, prefix=settings.API_V1_PREFIX)`
1 lan duy nhat, thay vi phai include tung file route rieng le.
"""

from fastapi import APIRouter

from src.api.v1 import analysis, auth, counselor, cvs, interviews, jds, students

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(cvs.router)
api_router.include_router(jds.router)
api_router.include_router(analysis.router)
api_router.include_router(interviews.router)
api_router.include_router(counselor.router)
api_router.include_router(students.router)
