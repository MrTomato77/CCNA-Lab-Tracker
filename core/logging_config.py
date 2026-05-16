"""Unified server logging.

Configures loguru as the single sink for the whole app and routes stdlib
`logging` records (Robyn, Actix, anything else third-party) through the same
formatter so the console has one consistent look.

Call `setup_logging()` exactly once at process startup, BEFORE Robyn() is
instantiated — Robyn registers its `robyn.logger` handler on import, so
hijacking has to happen first.

# TODO: services/pt_launcher.py, services/file_importer.py, database/seed.py
# all call `logger.info(...)` without `.bind(name=...)`, so they fall back to
# the "app" tag. Sharper console = wrap each module's logger with a per-module
# binding. Out of scope here.
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
        # "robyn.logger" / "actix_server.builder" → "robyn" / "actix_server"
        short = record.name.split(".")[0]
        # Don't pass depth= to opt() — the depth needed to climb out of stdlib
        # logging varies (5–9 frames depending on call path), and overshooting
        # raises "call stack is not deep enough". Caller info is irrelevant
        # here anyway — `extra[name]` already says where the record came from.
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
    # Default `extra[name]` so direct loguru callers (no .bind) don't KeyError
    # on the format string's {extra[name]} field.
    logger.configure(extra={"name": "app"})

    # Force Robyn's logger module to import NOW so its module-level code (which
    # attaches a colored StreamHandler to "robyn.logger") runs before our
    # hijack below. If we skip this, Robyn() gets instantiated later, imports
    # `robyn.logger` lazily, and re-attaches its StreamHandler on top of our
    # InterceptHandler — restoring the noisy raw output we tried to suppress.
    try:
        import robyn.logger  # noqa: F401
    except ImportError:
        warnings.warn(
            "robyn.logger not found - logging intercept may be incomplete",
            RuntimeWarning,
            stacklevel=2,
        )

    # Hijack stdlib logging.
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
        # WARNING cuts INFO chatter at the source — saves the filter from
        # running on every "Added route" record and protects us from any
        # future Robyn INFO line the filter doesn't know about yet.
        lg.setLevel(logging.WARNING)
