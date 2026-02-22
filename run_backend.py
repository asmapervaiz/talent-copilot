"""Run FastAPI backend. Use from project root: python run_backend.py"""
import uvicorn
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
