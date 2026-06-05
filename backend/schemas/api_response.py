from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Any = None
    error_code: str | None = None


def success_response(data: Any = None, message: str = "ok") -> ApiResponse:
    return ApiResponse(success=True, message=message, data=data, error_code=None)


def error_response(message: str, error_code: str, data: Any = None) -> ApiResponse:
    return ApiResponse(success=False, message=message, data=data, error_code=error_code)
