from enum import Enum


class OutboxStatusEnum(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
