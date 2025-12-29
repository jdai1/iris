"""Custom logging configuration for the scraper."""

import logging
import os
import sys


def setup_scraper_logging():
    """
    Configure logging to only show scraper logs, suppressing library noise.

    Sets up:
    - Custom logger named 'iris' for scraper logs
    - Root logger set to WARNING to suppress library debug/info
    - Custom formatter for cleaner output
    """
    # Get log level from environment
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Configure root logger to suppress library noise
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create console handler with custom formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level))

    # Custom formatter for scraper logs
    formatter = logging.Formatter(
        fmt="%(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Configure the 'iris' logger (our custom logger)
    iris_logger = logging.getLogger("iris")
    iris_logger.setLevel(getattr(logging, log_level))
    iris_logger.addHandler(handler)
    iris_logger.propagate = False  # Don't propagate to root logger

    return iris_logger


# Create the logger instance
scraper_logger = setup_scraper_logging()
