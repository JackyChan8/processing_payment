import hashlib
import json

from src.api.schemas import payment_schemas


def compute_hash(data: payment_schemas.PaymentCreate):
    """
    Создания хеша платежа
    """
    hash_data = json.dumps(
        {
            "amount": format(data.amount, ".2f"),
            "currency": data.currency.value,
            "description": data.description,
            "metadata": data.metadata,
            "webhook_url": str(data.webhook_url),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(hash_data.encode()).hexdigest()
