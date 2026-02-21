# webapp/backend/main.py
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI(title="UC2 Nachrichten-Triage", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


# Frontend statisch servieren
_frontend = Path(__file__).parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
