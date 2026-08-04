import os
import sys
import time
import logging
from datetime import datetime
from app.config import get_app_dir

# Ensure logs directory exists in app directory
LOGS_DIR = os.path.join(get_app_dir(), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)


def cleanup_old_logs(logs_dir: str = LOGS_DIR, max_files: int = 20, max_days: int = 30):
    """
    Cleans up old session logs:
    - Removes log files older than max_days (30 days).
    - Ensures total log file count does not exceed max_files (20 files).
    """
    if not os.path.exists(logs_dir):
        return

    now = time.time()
    max_age_seconds = max_days * 86400

    log_files = []
    for f in os.listdir(logs_dir):
        if f.endswith(".log"):
            full_path = os.path.join(logs_dir, f)
            if os.path.isfile(full_path):
                mtime = os.path.getmtime(full_path)
                log_files.append((full_path, mtime))

    # 1. Delete files older than 30 days
    remaining_files = []
    for path, mtime in log_files:
        if (now - mtime) > max_age_seconds:
            try:
                os.remove(path)
            except Exception:
                pass
        else:
            remaining_files.append((path, mtime))

    # 2. Limit to max_files (20 files). Delete oldest if > 20
    if len(remaining_files) > max_files:
        remaining_files.sort(key=lambda x: x[1])
        to_delete_count = len(remaining_files) - max_files
        for path, _ in remaining_files[:to_delete_count]:
            try:
                os.remove(path)
            except Exception:
                pass


# Run automatic log retention cleanup on logger import
cleanup_old_logs()

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
