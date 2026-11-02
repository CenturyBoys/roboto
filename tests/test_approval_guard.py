"""Anti-loopjacking (Trilha H): canonical rendering + comparação exata no uso."""

from __future__ import annotations

from roboto.app.approval_guard import ApprovedAction, action_digest, canonical_action, matches


def test_canonical_is_order_independent() -> None:
    a = canonical_action("Bash", {"cmd": "ls", "cwd": "/x"})
    b = canonical_action("Bash", {"cwd": "/x", "cmd": "ls"})
    assert a == b  # ordem dos args não muda a renderização canônica


def test_digest_stable_for_same_action() -> None:
    assert action_digest("Edit", {"file": "a.py"}) == action_digest("Edit", {"file": "a.py"})


def test_matches_identical_action() -> None:
    approved = ApprovedAction.sign("Bash", {"cmd": "deploy"})
    assert matches(approved, "Bash", {"cmd": "deploy"}) is True


def test_rejects_changed_argument() -> None:
    # loopjacking clássico: aprova um comando, tenta executar OUTRO.
    approved = ApprovedAction.sign("Bash", {"cmd": "echo oi"})
    assert matches(approved, "Bash", {"cmd": "rm -rf /"}) is False


def test_rejects_changed_tool() -> None:
    approved = ApprovedAction.sign("Read", {"file": "a.py"})
    assert matches(approved, "Write", {"file": "a.py"}) is False


def test_rejects_extra_argument() -> None:
    approved = ApprovedAction.sign("Bash", {"cmd": "ls"})
    assert matches(approved, "Bash", {"cmd": "ls", "sudo": True}) is False
