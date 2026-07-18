from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.deps import ApiError
from app.routers import (
    admin,
    guestbook,
    reservations,
    reserve,
    seats,
    shops,
    status,
    verify,
)

app = FastAPI(title="멈춰, 섬! API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    # D-24: 모든 실패 응답은 { error: { code, message } } 봉투로 통일한다.
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


app.include_router(status.router)
app.include_router(shops.router)
app.include_router(verify.router)
app.include_router(seats.router)
app.include_router(reserve.router)
app.include_router(reservations.router)
app.include_router(guestbook.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
