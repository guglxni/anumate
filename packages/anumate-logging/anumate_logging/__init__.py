"""Anumate logging utilities."""

import logging
import sys
from typing import Optional

def configure_root_logger(level: str = "INFO") -> logging.Logger:
    """Configure the root logger with basic settings."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    return logging.getLogger()

def setup_logging(level: str = "INFO") -> logging.Logger:
    """Setup logging configuration."""
    return configure_root_logger(level)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)