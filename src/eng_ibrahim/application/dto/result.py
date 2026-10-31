from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Result(Generic[T]):
    ok: bool
    value: T | None = None
    error_code: str | None = None
    message: str = ""

    @staticmethod
    def success(value: T | None = None) -> Result[T]:
        return Result(True, value)

    @staticmethod
    def failure(error_code: str, message: str = "") -> Result[T]:
        return Result(False, None, error_code, message)
