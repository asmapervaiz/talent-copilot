"""Run Streamlit frontend. Use from project root: python run_frontend.py"""
import os
import sys
import subprocess
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
os.chdir(frontend_dir)
subprocess.run([sys.executable, "-m", "streamlit", "run", "streamlit_app.py", "--server.port=8501"])
