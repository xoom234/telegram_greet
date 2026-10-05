"""Пользовательские ошибки с короткими текстами для ответа в Telegram."""
from __future__ import annotations

SERVICE_ACCOUNT_HINT = (
    "phomoikahoomgera@original-frame-510609-i7.iam.gserviceaccount.com"
)


class UserFacingError(Exception):
    """Исключение, текст которого можно показать пользователю."""

    def __init__(self, user_message: str) -> None:
        self.user_message = user_message
        super().__init__(user_message)


class SheetBusyError(UserFacingError):
    """Google API вернул 429 / исчерпан лимит после retry."""


class SheetNetworkError(UserFacingError):
    """Нет сети или таймаут при обращении к таблице."""


class SheetAccessError(UserFacingError):
    """Отозван или не выдан доступ сервисного аккаунта."""


def sheet_access_message(email: str | None = None) -> str:
    account = (email or "").strip() or SERVICE_ACCOUNT_HINT
    return (
        "Нет доступа к таблице. Проверьте, что доступ Редактор выдан "
        f"{account}"
    )
