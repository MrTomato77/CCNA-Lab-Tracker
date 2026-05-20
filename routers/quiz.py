"""HTTP routes for the Quiz/Practice module (v2)."""
from loguru import logger
from pydantic import ValidationError
from robyn import Request, Response, SubRouter

from core.responses import ErrorResponse, api_error, ok, validation_error
from models.quiz_schemas import AnswerSubmit, DontKnowSubmit, SessionStart
from services import image_service, quiz_service

router = SubRouter(__name__, prefix="/api/quiz")

_MAX_ANSWER_BODY = 512


def _parse_session_id(request: Request) -> tuple[int | None, ErrorResponse | None]:
    raw = request.path_params.get("id", "")
    try:
        sid = int(raw)
    except (TypeError, ValueError):
        return None, api_error("Invalid session id.", "INVALID_SESSION_ID", 400)
    if sid <= 0:
        return None, api_error("Invalid session id.", "INVALID_SESSION_ID", 400)
    return sid, None


# ───────────────────────── Dashboard ─────────────────────────

@router.get("/dashboard")
async def get_dashboard(request: Request) -> dict:
    return ok(await quiz_service.get_dashboard())


# ───────────────────────── Session lifecycle ─────────────────────────

@router.post("/sessions")
async def start_session(request: Request) -> dict | ErrorResponse:
    # Robyn 0.64's request.json() flattens nested values; using
    # model_validate_json keeps us consistent with /answers.
    try:
        data = SessionStart.model_validate_json(request.body)
    except ValidationError as e:
        return validation_error(e)
    try:
        sid, picked_n = await quiz_service.start_session(data.batch_size)
    except ValueError as e:
        return api_error(str(e), "INVALID_BATCH", 422)
    return ok({"session_id": sid, "picked_n": picked_n})


@router.get("/sessions/:id/next")
async def next_question(request: Request) -> dict | ErrorResponse:
    sid, err = _parse_session_id(request)
    if err:
        return err
    _, err = await quiz_service.require_session(sid)
    if err:
        return err
    return ok(await quiz_service.next_question(sid))


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
    try:
        data = AnswerSubmit.model_validate_json(request.body)
    except ValidationError as e:
        return validation_error(e)
    result = await quiz_service.submit_answer(sid, data.question_id, data.selected_labels)
    if result is None:
        return api_error("Question not found.", "QUESTION_NOT_FOUND", 404)
    if result is quiz_service.ALREADY_ANSWERED:
        return api_error(
            "Question already answered in this session.",
            "ALREADY_ANSWERED", 409,
        )
    return ok(result)


@router.post("/sessions/:id/dont-know")
async def dont_know(request: Request) -> dict | ErrorResponse:
    sid, err = _parse_session_id(request)
    if err:
        return err
    _, err = await quiz_service.require_session(sid)
    if err:
        return err
    try:
        data = DontKnowSubmit.model_validate_json(request.body)
    except ValidationError as e:
        return validation_error(e)
    result = await quiz_service.dont_know(sid, data.question_id)
    if result is None:
        return api_error("Question not found.", "QUESTION_NOT_FOUND", 404)
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
    _, err = await quiz_service.require_session(sid)
    if err:
        return err
    return ok(await quiz_service.get_summary(sid))


# ───────────────────────── Reset ─────────────────────────

@router.post("/reset")
async def reset_progress(request: Request) -> dict:
    cleared = await quiz_service.reset_progress()
    return ok({"cleared_progress": cleared, "cleared_sessions": False})


# ───────────────────────── Images ─────────────────────────

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
            "Content-Type":           content_type,
            "Cache-Control":          "public, max-age=86400",
            # Block browser content-sniffing — declared type must be
            # honoured even if the bytes look like HTML/SVG/anything else.
            "X-Content-Type-Options": "nosniff",
        },
        description=data,
    )
