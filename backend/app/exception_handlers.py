from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.schemas.api_response import error_response


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = str(exc.detail or "Request failed.")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(message=message, error_code=f"HTTP_{exc.status_code}").model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_response(
                message="Request validation failed.",
                error_code="VALIDATION_ERROR",
                data={"errors": exc.errors()},
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_response(message=str(exc) or "Internal server error.", error_code="INTERNAL_ERROR").model_dump(
                mode="json"
            ),
        )
