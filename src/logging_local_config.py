import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Any, Optional
from pathlib import Path

import logfire

# Configure local file logging
LOG_DIR = os.environ.get("LOG_DIR", "logs")
LOG_FILE = os.environ.get("LOG_FILE", "arc-lang.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG")
LOG_MAX_BYTES = int(
    os.environ.get("LOG_MAX_BYTES", str(10 * 1024 * 1024))
)  # 10MB default
LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", "5"))

# Create logs directory if it doesn't exist
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

# Set up the local logger
local_logger = logging.getLogger("arc-lang-local")
local_logger.setLevel(getattr(logging, LOG_LEVEL.upper()))

# Create file handler with rotation
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, LOG_FILE),
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
)

# Create formatter
formatter = logging.Formatter(
    "%(asctime)s - [%(levelname)s] - %(message)s - {%(context)s}",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler.setFormatter(formatter)

# Add handler to logger
local_logger.addHandler(file_handler)

# Optional: Also add console handler for local logging
if os.environ.get("LOG_TO_CONSOLE", "false").lower() == "true":
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    local_logger.addHandler(console_handler)


def _format_context(**kwargs: Any) -> str:
    """Format kwargs into a context string for local logging."""
    context_parts = []
    for key, value in kwargs.items():
        if value is not None:
            context_parts.append(f"{key}={value}")
    return ", ".join(context_parts)


def debug(msg: str, **kwargs: Any) -> None:
    """Log debug message to both local file and Logfire."""
    # Log to local file
    context = _format_context(**kwargs)
    local_logger.debug(msg, extra={"context": context})

    # Log to Logfire (will use your patched version with context)
    logfire.debug(msg, **kwargs)


def info(msg: str, **kwargs: Any) -> None:
    """Log info message to both local file and Logfire."""
    # Log to local file
    context = _format_context(**kwargs)
    local_logger.info(msg, extra={"context": context})

    # Log to Logfire
    logfire.info(msg, **kwargs)


def warn(msg: str, **kwargs: Any) -> None:
    """Log warning message to both local file and Logfire."""
    # Log to local file
    context = _format_context(**kwargs)
    local_logger.warning(msg, extra={"context": context})

    # Log to Logfire
    logfire.warn(msg, **kwargs)


def warning(msg: str, **kwargs: Any) -> None:
    """Alias for warn()."""
    warn(msg, **kwargs)


def error(msg: str, exc_info: Optional[bool] = None, **kwargs: Any) -> None:
    """Log error message to both local file and Logfire."""
    # Log to local file
    context = _format_context(**kwargs)
    local_logger.error(msg, exc_info=exc_info, extra={"context": context})

    # Log to Logfire
    if exc_info is not None:
        logfire.error(msg, _exc_info=exc_info, **kwargs)
    else:
        logfire.error(msg, **kwargs)


def trace(msg: str, **kwargs: Any) -> None:
    """Log trace message to both local file and Logfire."""
    # Log to local file (using DEBUG level since standard logging doesn't have TRACE)
    context = _format_context(**kwargs)
    local_logger.debug(f"[TRACE] {msg}", extra={"context": context})

    # Log to Logfire if trace is available
    if hasattr(logfire, "trace"):
        logfire.trace(msg, **kwargs)


def notice(msg: str, **kwargs: Any) -> None:
    """Log notice message to both local file and Logfire."""
    # Log to local file (using INFO level)
    context = _format_context(**kwargs)
    local_logger.info(f"[NOTICE] {msg}", extra={"context": context})

    # Log to Logfire if notice is available
    if hasattr(logfire, "notice"):
        logfire.notice(msg, **kwargs)


def fatal(msg: str, **kwargs: Any) -> None:
    """Log fatal message to both local file and Logfire."""
    # Log to local file (using CRITICAL level)
    context = _format_context(**kwargs)
    local_logger.critical(f"[FATAL] {msg}", extra={"context": context})

    # Log to Logfire if fatal is available
    if hasattr(logfire, "fatal"):
        logfire.fatal(msg, **kwargs)


def span(name: str, **kwargs: Any):
    """Create a span for both local logging and Logfire."""
    # Log span start to local file
    context = _format_context(**kwargs)
    local_logger.info(f"[SPAN START] {name}", extra={"context": context})

    # Create Logfire span
    span_context = logfire.span(name, **kwargs)

    # Wrap the span context to also log span end
    class SpanWrapper:
        def __init__(self, span_context, name, logger):
            self._span = span_context
            self._name = name
            self._logger = logger

        def __enter__(self):
            return self._span.__enter__()

        def __exit__(self, exc_type, exc_val, exc_tb):
            result = self._span.__exit__(exc_type, exc_val, exc_tb)
            # Log span end to local file
            if exc_type:
                self._logger.error(f"[SPAN END] {self._name} - ERROR: {exc_val}")
            else:
                self._logger.info(f"[SPAN END] {self._name}")
            return result

        def __getattr__(self, name):
            return getattr(self._span, name)

    return SpanWrapper(span_context, name, local_logger)


# Export convenience function to get the local logger directly if needed
def get_local_logger() -> logging.Logger:
    """Get the local logger instance for direct access."""
    return local_logger


# Log initialization
local_logger.info(
    f"Local logging initialized - writing to {os.path.join(LOG_DIR, LOG_FILE)}"
)
