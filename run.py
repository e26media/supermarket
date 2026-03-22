import subprocess
import sys
import time

def main():
    print("🚀 Starting Supermarket System...")

    # Start FastAPI Backend
    print("📦 Starting FastAPI Backend on http://localhost:8000 ...")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--reload", "--port", "8000"]
    )
    
    # Wait a moment for the backend to initialize
    time.sleep(2)
    
    # Start HTMX Frontend
    print("🎨 Starting HTMX Frontend on http://localhost:8001 ...")
    frontend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "frontend.routes:app", "--reload", "--port", "8001"]
    )
    
    print("\n✅ Both services are running!")
    print("Backend API : http://localhost:8000")
    print("Frontend UI : http://localhost:8001")
    print("Press Ctrl+C to stop both services.\n")
    
    try:
        backend.wait()
        frontend.wait()
    except KeyboardInterrupt:
        print("\n🛑 Stopping services...")
        backend.terminate()
        frontend.terminate()
        backend.wait()
        frontend.wait()
        print("Services stopped.")
        sys.exit(0)

if __name__ == "__main__":
    main()
