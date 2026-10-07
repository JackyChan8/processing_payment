class AppError(Exception):
    status_code: int = 500
    message: str = "Внутренняя ошибка сервера"

    def __init__(self, message: str | None = None):
        self.message = message or self.message
        super().__init__(self.message)


class IdempotencyKeyConfllctError(AppError):
    status_code = 409
    message = "Idempotenct-Key уже существует"


class PaymentNotFoundError(AppError):
    status_code = 404
    message = "Платеж не найден"
