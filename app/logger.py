import os
import sys
import logging
from datetime import datetime

# Garante que a pasta logs existe
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Gera nome de arquivo único para a sessão atual
session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
SESSION_LOG_FILE = os.path.join(LOGS_DIR, f"session_{session_timestamp}.log")


class FlushFileHandler(logging.FileHandler):
    """FileHandler que força o flush no disco após cada mensagem de log."""
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

        # File Handler (Salva em tempo real no disco por sessão)
        file_handler = FlushFileHandler(SESSION_LOG_FILE, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = setup_logger()
logger.info(f"Sessão iniciada. Salvando logs em tempo real em: {SESSION_LOG_FILE}")
