class PermanentError(Exception):
    """
    Неустранимая ошибка
    """

class PaymentBusyError(PermanentError):
    """
    Платеж занят другим воркером
    """


class WebhookTemporaryError(Exception):
    """
    Сбой при доставке уведомления
    """


class WebhookRejectedError(PermanentError):
    """
    Сервер-получатель отклоняет отправленный вебхук от сервера отправителя
    """
