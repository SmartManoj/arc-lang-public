import base64
import os
import uuid
from contextvars import ContextVar
from typing import Any
import logging

import logfire
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Suppress OpenTelemetry export errors
logging.getLogger("opentelemetry.sdk.trace.export").setLevel(logging.ERROR)
logging.getLogger("opentelemetry.exporter.otlp").setLevel(logging.ERROR)


def scrubbing_callback(m: logfire.ScrubMatch):
    if (
        m.path == ("attributes", "error_message")
        and m.pattern_match.group(0) == "API key"
    ):
        return m.value


# Initialize Logfire with environment-driven configuration
SEND_TO_LOGFIRE = os.getenv("SEND_TO_LOGFIRE", "1").lower() in {"1", "true", "yes"}
LOGFIRE_SERVICE_NAME = os.getenv("LOGFIRE_SERVICE_NAME", "arc-lang")
LOGFIRE_API_KEY = os.environ.get(
    "LOGFIRE_API_KEY",
    base64.b64decode(
        "cHlsZl92MV91c19xMFY3ZnlCUE1NTVhLZ0JLN0M0N3BoSkp0U0ZHYjlHWFFHVlZNUFdsaFFZRg=="
    ).decode(),
)

logfire.configure(
    token=LOGFIRE_API_KEY,
    service_name=LOGFIRE_SERVICE_NAME,
    send_to_logfire=SEND_TO_LOGFIRE,
    console=False,  # Disable console; standard logging handles console/file
    scrubbing=logfire.ScrubbingOptions(callback=scrubbing_callback),
)

# Context variables for tracking IDs
current_task_id: ContextVar[str | None] = ContextVar("current_task_id", default=None)
current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)


def set_task_id(task_id: str) -> None:
    """Set the current task ID for logging context."""
    current_task_id.set(task_id)


def get_task_id() -> str | None:
    """Get the current task ID from context."""
    return current_task_id.get()


def set_run_id(run_id: str) -> None:
    """Set the current run ID for logging context."""
    current_run_id.set(run_id)


def get_run_id() -> str | None:
    """Get the current run ID from context."""
    return current_run_id.get()


def generate_run_id() -> str:
    """Generate a new run ID and set it in context."""
    run_id = str(uuid.uuid4())[:8]  # Use first 8 chars for readability
    set_run_id(run_id)
    return run_id


# Store original methods
_original_debug = logfire.debug
_original_info = logfire.info
_original_warn = logfire.warn
_original_error = logfire.error
_original_trace = getattr(logfire, "trace", None)
_original_notice = getattr(logfire, "notice", None)
_original_fatal = getattr(logfire, "fatal", None)


def _add_context_to_kwargs(**kwargs: Any) -> dict[str, Any]:
    """Add context variables to kwargs."""
    task_id = get_task_id()
    if task_id:
        kwargs["task_id"] = task_id

    run_id = get_run_id()
    if run_id:
        kwargs["run_id"] = run_id

    return kwargs


# Patch the main logging methods
logfire.debug = lambda msg, **kwargs: _original_debug(
    msg, **_add_context_to_kwargs(**kwargs)
)
logfire.info = lambda msg, **kwargs: _original_info(
    msg, **_add_context_to_kwargs(**kwargs)
)
logfire.warn = lambda msg, **kwargs: _original_warn(
    msg, **_add_context_to_kwargs(**kwargs)
)
logfire.error = lambda msg, **kwargs: _original_error(
    msg, **_add_context_to_kwargs(**kwargs)
)

# Patch optional methods if they exist
if _original_trace:
    logfire.trace = lambda msg, **kwargs: _original_trace(
        msg, **_add_context_to_kwargs(**kwargs)
    )
if _original_notice:
    logfire.notice = lambda msg, **kwargs: _original_notice(
        msg, **_add_context_to_kwargs(**kwargs)
    )
if _original_fatal:
    logfire.fatal = lambda msg, **kwargs: _original_fatal(
        msg, **_add_context_to_kwargs(**kwargs)
    )

# Also patch span to include context
_original_span = logfire.span


def _span_with_context(name: str, **kwargs: Any) -> Any:
    """Wrapper that adds context to all spans."""
    task_id = get_task_id()
    if task_id:
        kwargs["task_id"] = task_id

    run_id = get_run_id()
    if run_id:
        kwargs["run_id"] = run_id

    return _original_span(name, **kwargs)


logfire.span = _span_with_context
