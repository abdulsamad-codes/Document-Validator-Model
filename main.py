"""
Main entrypoint for the KPITB Document Verification System.

Usage:
    # Start API server:
    python main.py api

    # Start Streamlit dashboard:
    python main.py dashboard

    # Run all tests:
    python main.py test
"""

import sys
import io
import subprocess
from pathlib import Path

# Fix UnicodeEncodeError on Windows when printing emoji characters.
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
VENV_PYTHON = BASE_DIR / "Myenv" / "Scripts" / "python.exe"


def start_api():
    """Start the FastAPI server via uvicorn."""
    print("🚀 Starting FastAPI server on http://localhost:8000")
    print("   Docs: http://localhost:8000/docs")
    subprocess.run([
        str(VENV_PYTHON), "-m", "uvicorn",
        "app.api.endpoints:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload"
    ], cwd=str(BASE_DIR))


def start_dashboard():
    """Start the Streamlit dashboard."""
    print("🖥️  Starting Streamlit dashboard on http://localhost:8501")
    subprocess.run([
        str(VENV_PYTHON), "-m", "streamlit", "run",
        str(BASE_DIR / "dashboard" / "app.py"),
        "--server.port", "8501",
        "--server.headless", "true"
    ], cwd=str(BASE_DIR))


def run_tests():
    """Run the full test suite with pytest."""
    print("🧪 Running full test suite...")
    result = subprocess.run([
        str(VENV_PYTHON), "-m", "pytest",
        "tests/", "-v", "--tb=short"
    ], cwd=str(BASE_DIR))
    sys.exit(result.returncode)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Available commands: api, dashboard, test")
        sys.exit(1)

    command = sys.argv[1].lower()
    
    if command == "api":
        start_api()
    elif command == "dashboard":
        start_dashboard()
    elif command == "test":
        run_tests()
    else:
        print(f"Unknown command: {command}")
        print("Available commands: api, dashboard, test")
        sys.exit(1)


if __name__ == "__main__":
    main()
