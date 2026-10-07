from sqlalchemy import BigInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
        Базовый класс для всех моделей SQLAlchemy
    """


class BigIntegerPrimaryKeyMixin:
    """
        Миксин для добавления BigInteger первичного ключа
    """
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )


class BaseModel(Base, BigIntegerPrimaryKeyMixin):
    """
        Абстрактная базовая модель с BigInteger ID
    """
    __abstract__ = True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"
