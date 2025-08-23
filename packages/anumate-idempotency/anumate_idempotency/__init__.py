from __future__ import annotations

import functools
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Protocol

import redis


class IdempotencyKeyExists(Exception):
    pass


class IdempotencyStorage(Protocol):
    def get(self, key: str) -> Any:
        ...

    def set(self, key: str, value: Any) -> None:
        ...


class RedisIdempotencyStorage:
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    def get(self, key: str) -> Any:
        return self.client.get(key)

    def set(self, key: str, value: Any) -> None:
        if not self.client.set(key, value, nx=True):
            raise IdempotencyKeyExists()


class InMemoryIdempotencyStorage:
    def __init__(self) -> None:
        self.storage: Dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self.storage.get(key)

    def set(self, key: str, value: Any) -> None:
        if key in self.storage:
            raise IdempotencyKeyExists()
        self.storage[key] = value


def idempotent(
    storage: IdempotencyStorage,
    key_func: Callable[..., str],
) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = key_func(*args, **kwargs)
            try:
                storage.set(key, "processing")
            except IdempotencyKeyExists:
                return storage.get(key)

            result = func(*args, **kwargs)
            storage.set(key, result)
            return result

        return wrapper

    return decorator
