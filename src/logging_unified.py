"""
Unified logging module that sends logs to both Logfire and local files.
This provides the main logging interface for the application.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# Import the context-enriched Logfire functions and context management
from .logging_config import (
    _original_debug,
    _original_info,
    _original_warn,
    _original_error,
    _original_trace,
    _original_notice,
    _original_fatal,
    _original_span,
    _add_context_to_kwargs,
    get_task_id,
    get_run_id,
    set_task_id,
    set_run_id,
    generate_run_id,
)

# Set up local file logging
LOG_DIR = os.environ.get("LOG_DIR", "logs")
LOG_FILE = os.environ.get("LOG_FILE", "arc-lang.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG")
LOG_MAX_BYTES = int(os.environ.get("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10MB
LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", "5"))

# Create logs directory if it doesn't exist
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

class _ContextFilter(logging.Filter):
    """Ensure a 'context' field exists on all records so formatting never fails."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if not hasattr(record, "context"):
            record.context = ""
        return True


# Set up the local logger
local_logger = logging.getLogger("arc-lang-local")
local_logger.setLevel(getattr(logging, LOG_LEVEL.upper()))
local_logger.propagate = False  # Prevent duplicate logs
_context_filter = _ContextFilter()
local_logger.addFilter(_context_filter)

# Create formatter
formatter = logging.Formatter(
    '%(asctime)s - [%(levelname)s] - %(message)s - {%(context)s}',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Add file/console handlers only once
if not local_logger.handlers:
    # Create file handler with rotation
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, LOG_FILE),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_context_filter)
    local_logger.addHandler(file_handler)

    # Optional: Also add console handler for local logging
    if os.environ.get("LOG_TO_CONSOLE", "false").lower() == "true":
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.addFilter(_context_filter)
        local_logger.addHandler(console_handler)

# Ensure any pre-existing handlers get the context filter (e.g., on reload)
for _h in list(local_logger.handlers):
    _h.addFilter(_context_filter)


def _format_local_context(**kwargs: Any) -> str:
    """Format kwargs into a context string for local logging."""
    context_parts = []
    for key, value in kwargs.items():
        if value is not None:
            context_parts.append(f"{key}={value}")
    return ", ".join(context_parts)


# Create unified logging functions that send to both Logfire and local file
def debug(msg: str, **kwargs: Any) -> None:
    """Log debug message to both local file and Logfire."""
    enriched_kwargs = _add_context_to_kwargs(**kwargs)
    
    # Log to local file
    context = _format_local_context(**enriched_kwargs)
    local_logger.debug(msg, extra={"context": context})
    
    # Log to Logfire
    _original_debug(msg, **enriched_kwargs)


def info(msg: str, **kwargs: Any) -> None:
    """Log info message to both local file and Logfire."""
    enriched_kwargs = _add_context_to_kwargs(**kwargs)
    
    # Log to local file
    context = _format_local_context(**enriched_kwargs)
    local_logger.info(msg, extra={"context": context})
    
    # Log to Logfire
    _original_info(msg, **enriched_kwargs)


def warn(msg: str, **kwargs: Any) -> None:
    """Log warning message to both local file and Logfire."""
    enriched_kwargs = _add_context_to_kwargs(**kwargs)
    
    # Log to local file
    context = _format_local_context(**enriched_kwargs)
    local_logger.warning(msg, extra={"context": context})
    
    # Log to Logfire
    _original_warn(msg, **enriched_kwargs)


def warning(msg: str, **kwargs: Any) -> None:
    """Alias for warn()."""
    warn(msg, **kwargs)


def error(msg: str, **kwargs: Any) -> None:
    """Log error message to both local file and Logfire."""
    # Handle _exc_info if present
    exc_info = kwargs.pop("_exc_info", None)
    
    enriched_kwargs = _add_context_to_kwargs(**kwargs)
    
    # Log to local file
    context = _format_local_context(**enriched_kwargs)
    local_logger.error(msg, exc_info=exc_info, extra={"context": context})
    
    # Log to Logfire
    if exc_info is not None:
        _original_error(msg, _exc_info=exc_info, **enriched_kwargs)
    else:
        _original_error(msg, **enriched_kwargs)


def exception(msg: str, **kwargs: Any) -> None:
    """Log exception with traceback to both local file and Logfire."""
    error(msg, _exc_info=True, **kwargs)


def trace(msg: str, **kwargs: Any) -> None:
    """Log trace message to both local file and Logfire."""
    if _original_trace:
        enriched_kwargs = _add_context_to_kwargs(**kwargs)
        
        # Log to local file (using DEBUG level)
        context = _format_local_context(**enriched_kwargs)
        local_logger.debug(f"[TRACE] {msg}", extra={"context": context})
        
        # Log to Logfire
        _original_trace(msg, **enriched_kwargs)


def notice(msg: str, **kwargs: Any) -> None:
    """Log notice message to both local file and Logfire."""
    if _original_notice:
        enriched_kwargs = _add_context_to_kwargs(**kwargs)
        
        # Log to local file (using INFO level)
        context = _format_local_context(**enriched_kwargs)
        local_logger.info(f"[NOTICE] {msg}", extra={"context": context})
        
        # Log to Logfire
        _original_notice(msg, **enriched_kwargs)


def fatal(msg: str, **kwargs: Any) -> None:
    """Log fatal message to both local file and Logfire."""
    if _original_fatal:
        enriched_kwargs = _add_context_to_kwargs(**kwargs)
        
        # Log to local file (using CRITICAL level)
        context = _format_local_context(**enriched_kwargs)
        local_logger.critical(f"[FATAL] {msg}", extra={"context": context})
        
        # Log to Logfire
        _original_fatal(msg, **enriched_kwargs)


def critical(msg: str, **kwargs: Any) -> None:
    """Alias for fatal() to match standard logging API."""
    fatal(msg, **kwargs)


def span(name: str, **kwargs: Any):
    """Create a span for both local logging and Logfire."""
    enriched_kwargs = _add_context_to_kwargs(**kwargs)
    
    # Log span start to local file
    context = _format_local_context(**enriched_kwargs)
    local_logger.info(f"[SPAN START] {name}", extra={"context": context})
    
    # Create Logfire span
    span_context = _original_span(name, **enriched_kwargs)
    
    # Wrap the span context to also log span end
    class SpanWrapper:
        def __init__(self, span_context, name, logger, context):
            self._span = span_context
            self._name = name
            self._logger = logger
            self._context = context
        
        def __enter__(self):
            return self._span.__enter__()
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            result = self._span.__exit__(exc_type, exc_val, exc_tb)
            # Log span end to local file
            if exc_type:
                self._logger.error(f"[SPAN END] {self._name} - ERROR: {exc_val}", extra={"context": self._context})
            else:
                self._logger.info(f"[SPAN END] {self._name}", extra={"context": self._context})
            return result
        
        def __getattr__(self, name):
            return getattr(self._span, name)
    
    return SpanWrapper(span_context, name, local_logger, context)


# Export context management functions for convenience
__all__ = [
    'debug',
    'info',
    'warn',
    'warning',
    'exception',
    'error',
    'trace',
    'notice',
    'fatal',
    'critical',
    'span',
    'set_task_id',
    'get_task_id',
    'set_run_id',
    'get_run_id',
    'generate_run_id',
]

# Log initialization
local_logger.info(
    f"Unified logging initialized - writing to {os.path.join(LOG_DIR, LOG_FILE)}"
)