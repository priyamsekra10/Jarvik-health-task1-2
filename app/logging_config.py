import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

def setup_logging():
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure logging format
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Setup file handler for all logs
    file_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(log_format)
    
    # Setup error file handler
    error_handler = RotatingFileHandler(
        'logs/error.log',
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    error_handler.setFormatter(log_format)
    error_handler.setLevel(logging.ERROR)
    
    # Setup console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    
    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)
    
    return logger