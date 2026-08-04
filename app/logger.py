import os
import sys
import logging
from datetime import datetime
from app.config import get_app_dir

# Ensure logs directory exists in app directory
LOGS_DIR = os.path.join(get_app_dir(), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Generate unique session filename
session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
SESSION_LOG_FILE = os.path.join(LOGS_DIR, f"session_{session_timestamp}.log")


class FlushFileHandler(logging.FileHandler):
    """FileHandler that forces immediate disk flush after every log record."""
    def emit(self, record):
        super().emit(record)
        self.flush()


def setup_logger(name: str = "nim_proxy") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Stream Handler (Console)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File Handler (Flushes to disk per session in real-time)
        file_handler = FlushFileHandler(SESSION_LOG_FILE, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = setup_logger()
logger.info(f"Session started. Saving real-time logs to: {SESSION_LOG_FILE}")
