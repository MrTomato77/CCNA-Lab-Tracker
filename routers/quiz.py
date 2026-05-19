"""HTTP routes for the Quiz/Practice module."""
from loguru import logger
from pydantic import ValidationError
from robyn import Request, Response, SubRouter

from core.responses import ErrorResponse, api_error, ok, validation_error
from models.quiz_schemas import AnswerSubmit, SessionStart
from services import image_service, quiz_service

router = SubRouter(__name__, prefix="/api/quiz")


def _parse_session_id(request: Request) -> tuple[int | None, ErrorResponse | None]:
    raw = request.path_params.get("id", "")
    try:
        sid = int(raw)
    except (TypeError, ValueError):
        return None, api_error("Invalid session id.", "INVALID_SESSION_ID", 400)
    if sid <= 0:
        return None, api_error("Invalid session id.", "INVALID_SESSION_ID", 400)
    return sid, None


@router.get("/pools")
async def list_pools(request: Request) -> dict:
    return ok(await quiz_service.list_pools())


@router.post("/sessions")
async def start_session(request: Request) -> dict | ErrorResponse:
    try:
        data = SessionStart.model_validate(request.json())
    except ValidationError as e:
        return validation_error(e)
    sid = await quiz_service.start_session(data.pool)
    return ok({"session_id": sid})


@router.get("/sessions/:id/next")
async def next_question(request: Request) -> dict | ErrorResponse:
    sid, err = _parse_session_id(request)
    if err:
        return err
    _, err = await quiz_service.require_session(sid)
    if err:
        return err
    return ok(await quiz_service.next_question(sid))  # None when pool exhausted


_MAX_ANSWER_BODY = 512


@router.post("/sessions/:id/answers")
async def submit_answer(request: Request) -> dict | ErrorResponse:
    sid, err = _parse_session_id(request)
    if err:
        return err
    _, err = await quiz_service.require_session(sid)
    if err:
        return err
    if len(request.body) > _MAX_ANSWER_BODY:
        return api_error("Payload too large.", "PAYLOAD_TOO_LARGE", 413)
    # Robyn 0.64's request.json() flattens nested values to strings, so a
    # list field arrives as a JSON-encoded string. Parse the raw body instead.
    try:
        data = AnswerSubmit.model_validate_json(request.body)
    except ValidationError as e:
        return validation_error(e)
    result = await quiz_service.submit_answer(sid, data.question_id, data.selected_labels)
    if result is None:
        return api_error(
            "Question not found or already answered in this session.",
            "QUESTION_UNAVAILABLE",
            404,
        )
    return ok(result)


@router.post("/sessions/:id/finish")
async def finish_session(request: Request) -> dict | ErrorResponse:
    sid, err = _parse_session_id(request)
    if err:
        return err
    _, err = await quiz_service.require_session(sid)
    if err:
        return err
    return ok(await quiz_service.finish_session(sid))


@router.get("/sessions/:id/summary")
async def get_summary(request: Request) -> dict | ErrorResponse:
    sid, err = _parse_session_id(request)
    if err:
        return err
    summary = await quiz_service.get_summary(sid)
    if summary is None:
        return api_error("Session not found.", "SESSION_NOT_FOUND", 404)
    return ok(summary)


@router.get("/images/:filename")
async def get_image(request: Request) -> Response:
    filename = request.path_params.get("filename", "")
    try:
        result = await image_service.read_image(filename)
    except Exception:
        logger.bind(name="api").exception("read_image failed for %s", filename)
        return Response(
            status_code=500,
            headers={"Content-Type": "text/plain"},
            description="Internal error",
        )
    if result is None:
        return Response(
            status_code=404,
            headers={"Content-Type": "text/plain"},
            description="Not found",
        )
    data, content_type = result
    return Response(
        status_code=200,
        headers={
            "Content-Type":  content_type,
            "Cache-Control": "public, max-age=86400",
        },
        description=data,
    )
