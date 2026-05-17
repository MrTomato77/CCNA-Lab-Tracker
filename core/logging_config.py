"""Unified server logging.

Routes all stdlib logging (Robyn, Actix, third-party) through loguru.
Call setup_logging() once at startup BEFORE Robyn() is instantiated —
Robyn registers its robyn.logger handler on import, so the hijack must happen first.
"""

import logging
import os
import sys
import warnings

from loguru import logger

# Robyn / Actix emit a fixed set of registration-time INFO lines that have
# no value at runtime — drop them by message substring.
_NOISY_MESSAGES = (
    "Added route",
    "VERBOSE/DEBUG MODE",
    "Added event",
    "Docs hosted at",
    "Robyn version",
    "Starting server at",
    "starting service",
    "Actix runtime found",
    "starting 1 workers",
)


class InterceptHandler(logging.Handler):
    """Forward stdlib logging records into loguru, dropping known noise."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if any(s in msg for s in _NOISY_MESSAGES):
            return
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        short = record.name.split(".")[0]  # "robyn.logger" → "robyn"
        # Don't pass depth= to opt() — the climb depth varies (5-9 frames) and
        # overshooting raises "call stack is not deep enough".
        logger.bind(name=short).opt(exception=record.exc_info).log(level, msg)


def setup_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        colorize=True,
        format=(
            "<dim>{time:HH:mm:ss}</dim>  "
            "<level>{level:<5}</level>  "
            "<cyan>{extra[name]:<11}</cyan> ·  "
            "<level>{message}</level>"
        ),
    )
    # Default extra[name] so callers without .bind() don't KeyError on the format string.
    logger.configure(extra={"name": "app"})

    # Force robyn.logger to import now so its module-level StreamHandler runs
    # before our hijack — otherwise Robyn() lazily re-attaches it on top of us.
    try:
        import robyn.logger  # noqa: F401
    except ImportError:
        warnings.warn(
            "robyn.logger not found - logging intercept may be incomplete",
            RuntimeWarning,
            stacklevel=2,
        )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in (
        "robyn",
        "robyn.logger",
        "actix_server",
        "actix_server.builder",
        "actix_server.server",
        "uvicorn",
        "uvicorn.access",
    ):
        lg = logging.getLogger(name)
        lg.handlers = [InterceptHandler()]
        lg.propagate = False
        lg.setLevel(logging.WARNING)  # cut INFO chatter at source
