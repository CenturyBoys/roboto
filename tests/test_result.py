"""Testes do tipo Result (tier 1 — determinístico, sem LLM)."""

from __future__ import annotations

from roboto.result import Err, Ok, Result


def _div(a: int, b: int) -> Result[int, str]:
    if b == 0:
        return Err("divisao por zero")
    return Ok(a // b)


def test_ok_basics() -> None:
    r = _div(10, 2)
    assert r.is_ok and not r.is_err
    assert r.unwrap() == 5
    assert r.unwrap_or(0) == 5


def test_err_basics() -> None:
    r = _div(1, 0)
    assert r.is_err and not r.is_ok
    assert r.unwrap_or(-1) == -1


def test_map_and_then() -> None:
    assert _div(10, 2).map(lambda x: x + 1).unwrap() == 6
    assert _div(1, 0).map(lambda x: x + 1).unwrap_or(-1) == -1
    chained = _div(100, 2).and_then(lambda x: _div(x, 5))
    assert chained.unwrap() == 10
    short = _div(1, 0).and_then(lambda x: _div(x, 5))
    assert short.is_err


def test_map_err() -> None:
    assert _div(1, 0).map_err(lambda e: f"erro: {e}").unwrap_or("x") == "x"


if __name__ == "__main__":
    # Permite rodar sem pytest: `python3 tests/test_result.py`
    import sys

    sys.path.insert(0, "src")
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("todos os testes passaram")
