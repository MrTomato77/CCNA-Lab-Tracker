"""Shared response helpers for Robyn route handlers.

Robyn 0.64 expects error responses as a 3-tuple `(body, headers_dict,
status_code)`. Two snags trip up the obvious form:
  1. A 2-tuple `(body, status)` raises ValueError inside Robyn's router
     and surfaces as a generic 500 — every 4xx in this codebase had
     been hidden that way until the new 404 guards finally triggered
     an error path during testing.
  2. Robyn's `_format_tuple_response` does
        `new_headers = Headers(headers)`
     then `headers.set("Content-Type", ...)` if the constructed
     Headers contains it. Passing a dict with `Content-Type` fails the
     second call (`dict` has no `.set`); passing a `Headers` object
     fails the first (its constructor wants a plain dict).
     The only stable input is an empty dict — Robyn's
     `_format_response` already stamps `application/json` on dict
     bodies, so omitting Content-Type from the tuple's headers dict
     loses nothing.
"""


ErrorResponse = tuple[dict, dict, int]


def err(body: dict, status: int) -> ErrorResponse:
    """Build a Robyn-compatible error response tuple. Headers stay
    empty on purpose — see module docstring for the Robyn quirk."""
    return body, {}, status
