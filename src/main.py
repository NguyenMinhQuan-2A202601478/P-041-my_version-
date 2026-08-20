from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import api_router
from src.config import settings
from src.core.errors import register_exception_handlers
from src.db.database import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Tao bang database (neu chua ton tai) 1 lan khi app khoi dong. Xem giai
    # thich chi tiet trong src/db/database.py::create_tables().
    create_tables()
    yield


app = FastAPI(
    title="CV Assistant API",
    description="Agent tối ưu CV theo JD và phỏng vấn thử STAR",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS (Cross-Origin Resource Sharing): frontend Next.js chay o 1
# domain/port khac backend (vd localhost:3000 vs localhost:8000). Neu khong
# co middleware nay, trinh duyet se tu chan moi request tu frontend toi
# backend vi ly do bao mat mac dinh cua trinh duyet.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
