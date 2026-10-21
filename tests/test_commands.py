"""Parsing de intenção do chat (determinístico): list / pick / discuss / ideia nova."""

from __future__ import annotations

from roboto.app.commands import parse_command


def test_pick() -> None:
    assert parse_command("pega #180") == ("pick", "180")
    assert parse_command("trabalha 42") == ("pick", "42")


def test_list_variants() -> None:
    assert parse_command("issues") == ("list", "")
    assert parse_command("qual issue conseguimos fazer que não bloqueada") == ("list", "")
    assert parse_command("quais issues abertas?") == ("list", "")
    assert parse_command("o que tem pra fazer") == ("list", "")


def test_discuss_existing_issue_reference() -> None:
    assert parse_command("sobre a issue 180") == ("discuss", "180")
    assert parse_command("a #180 precisa cobrir rate limit por IP") == ("discuss", "180")
    assert parse_command("issue #7") == ("discuss", "7")


def test_help_and_greetings() -> None:
    for t in ["ajuda", "help", "/help", "/start", "oi", "olá", "ola", "comandos", "bom dia"]:
        assert parse_command(t) == ("help", ""), t


def test_new_idea_is_not_a_command() -> None:
    assert parse_command("quero um placar de vitórias por jogador") is None
    assert parse_command("adicionar botão de login") is None
