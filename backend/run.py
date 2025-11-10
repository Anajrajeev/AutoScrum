"""
Quick start script for AutoScrum backend.

Usage:
    python run.py
"""

import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Get configuration
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    
    print("=" * 60)
    print("AutoScrum Backend Starting...")
    print("=" * 60)
    print(f"Server: http://{host}:{port}")
    print(f"API Docs: http://{host}:{port}/docs")
    print(f"ReDoc: http://{host}:{port}/redoc")
    print(f"Health: http://{host}:{port}/health")
    print("=" * 60)
    print()
    
    # Run server
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )

