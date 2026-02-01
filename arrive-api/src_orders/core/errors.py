class AppError(Exception):
    code: str = "APP_ERROR"
    http_status: int = 500
    message: str = "internal error"

    def to_dict(self):
        return {"error": {"code": self.code, "message": self.message}}


class ValidationError(AppError):
    code = "VALIDATION"
    http_status = 400
    message = "validation failed"


class NotFoundError(AppError):
    code = "NOT_FOUND"
    http_status = 404
    message = "not found"


class ExpiredError(AppError):
    code = "EXPIRED"
    http_status = 409
    message = "order expired"


class InvalidStateError(AppError):
    code = "INVALID_STATE"
    http_status = 409
    message = "invalid state transition"

