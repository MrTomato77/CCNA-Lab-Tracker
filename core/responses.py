"""Shared response helpers for Robyn route handlers.

Robyn 0.64 error responses must be a 3-tuple (body, headers_dict, status_code):
  - A 2-tuple raises ValueError inside the router and surfaces as a 500.
  - The headers dict must be empty — passing Content-Type breaks Robyn's
    _format_tuple_response (dict has no .set). Robyn stamps application/json
    on dict bodies automatically, so the omission is safe.
"""


from typing import Any

from pydantic import ValidationError


ErrorResponse = tuple[dict, dict, int]


def err(body: dict, status: int) -> ErrorResponse:
    """Build a Robyn error response tuple (empty headers — see module docstring)."""
    return body, {}, status


def ok(data: Any | None = None, message: str | None = None) -> dict:
    body: dict[str, Any] = {"success": True}
    if data is not None:
        body["data"] = data
    if message is not None:
        body["message"] = message
    return body


def api_error(error: str, code: str, status: int) -> ErrorResponse:
    return err({"success": False, "error": error, "code": code}, status)


def validation_error(exc: ValidationError) -> ErrorResponse:
    return api_error(exc.errors()[0]["msg"], "VALIDATION_ERROR", 422)


def lab_not_found(lab_id: str | None) -> ErrorResponse:
    return api_error(f"Lab {lab_id} not found.", "LAB_NOT_FOUND", 404)


def internal_error(code: str) -> ErrorResponse:
    return api_error("An internal error occurred.", code, 500)
