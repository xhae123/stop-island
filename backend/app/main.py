from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import admin, guestbook, reserve, seats, shops, status, verify

app = FastAPI(title="멈춰, 섬! API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(status.router)
app.include_router(shops.router)
app.include_router(verify.router)
app.include_router(seats.router)
app.include_router(reserve.router)
app.include_router(guestbook.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
