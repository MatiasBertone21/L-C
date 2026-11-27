from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str = "app_error",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.headers = headers


class UnauthorizedError(AppException):
    def __init__(self, message: str = "No autenticado o credenciales inválidas") -> None:
        super().__init__(
            message=message,
            status_code=401,
            code="unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenError(AppException):
    def __init__(self, message: str = "No tiene permisos suficientes para realizar esta acción") -> None:
        super().__init__(message=message, status_code=403, code="forbidden")


class NotFoundError(AppException):
    def __init__(self, message: str = "Recurso no encontrado") -> None:
        super().__init__(message=message, status_code=404, code="not_found")


class DuplicateResourceError(AppException):
    def __init__(self, message: str = "El recurso ya existe") -> None:
        super().__init__(message=message, status_code=409, code="duplicate_resource")


class DomainValidationError(AppException):
    def __init__(self, message: str = "Datos de solicitud inválidos") -> None:
        super().__init__(message=message, status_code=400, code="validation_error")


class ServiceUnavailableError(AppException):
    def __init__(self, message: str = "Servicio temporalmente no disponible") -> None:
        super().__init__(message=message, status_code=503, code="service_unavailable")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(_request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code},
            headers=exc.headers,
        )
