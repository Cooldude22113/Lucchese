from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.database import init_db
from routes.chat import router as chat_router
from routes.admin import router as admin_router
from routes.conversations import router as conv_router
from routes.files import router as files_router
from routes.voice import router as voice_router
from routes.shopify import router as shopify_router
from routes.deal import router as deal_router
from routes import state

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://192.168.1.112:5173",
        "https://lucchese.app",
        "https://www.lucchese.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(conv_router)
app.include_router(files_router)
app.include_router(voice_router)
app.include_router(shopify_router)
app.include_router(deal_router)
app.include_router(state.router)