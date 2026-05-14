from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from api.routers import contractors, notices

app = FastAPI(title="施工店支払通知書発行システム")

app.include_router(contractors.router)
app.include_router(notices.router)

app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")
