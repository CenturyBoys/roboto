"""Tipo Result estilo Rust (decisão D1): ok/erro explícito no retorno.

Regra do projeto: **não usar exceções para fluxo de controle** — operações que podem falhar
retornam ``Result[T, E]`` (``Ok(value)`` ou ``Err(error)``). Exceção fica para erro de
programação/inesperado, não para o fluxo esperado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, NoReturn, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")
F = TypeVar("F")


@dataclass(frozen=True)
class Ok(Generic[T]):
    """Resultado de sucesso, carregando ``value``."""

    value: T
    is_ok: bool = True
    is_err: bool = False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value

    def map(self, fn: Callable[[T], U]) -> "Result[U, E]":
        return Ok(fn(self.value))

    def map_err(self, fn: Callable[[E], F]) -> "Result[T, F]":
        return self

    def and_then(self, fn: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        return fn(self.value)


@dataclass(frozen=True)
class Err(Generic[E]):
    """Resultado de erro, carregando ``error`` (valor, não exceção lançada)."""

    error: E
    is_ok: bool = False
    is_err: bool = True

    def unwrap(self) -> NoReturn:
        raise RuntimeError(f"unwrap() chamado em Err: {self.error!r}")

    def unwrap_or(self, default: T) -> T:
        return default

    def map(self, fn: Callable[[T], U]) -> "Result[U, E]":
        return self

    def map_err(self, fn: Callable[[E], F]) -> "Result[T, F]":
        return Err(fn(self.error))

    def and_then(self, fn: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        return self


Result = Union[Ok[T], Err[E]]
"""Um ``Result`` é ``Ok[T]`` ou ``Err[E]``."""
