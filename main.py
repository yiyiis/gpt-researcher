from dotenv import load_dotenv
import logging
import os
import sys
from pathlib import Path

# Load .env from the correct location:
# - Compiled executable: same directory as the .exe
# - Normal Python: current working directory (default behavior)
if getattr(sys, 'frozen', False):
    # Running as compiled executable (PyInstaller, Nuitka, etc.)
    env_path = os.path.join(os.path.dirname(sys.executable), ".env")
    load_dotenv(env_path)
else:
    load_dotenv()

# Create logs directory if it doesn't exist
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # File handler for general application logs
        logging.FileHandler('logs/app.log'),
        # Stream handler for console output
        logging.StreamHandler()
    ]
)

# Suppress verbose fontTools logging
logging.getLogger('fontTools').setLevel(logging.WARNING)
logging.getLogger('fontTools.subset').setLevel(logging.WARNING)
logging.getLogger('fontTools.ttLib').setLevel(logging.WARNING)

# Create logger instance
logger = logging.getLogger(__name__)

load_dotenv()

from backend.server.app import app

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
