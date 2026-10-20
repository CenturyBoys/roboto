"""Adapter de git por subprocess (IO real; não exercitado no CI). Implementa a porta GitOps.

Usado no container do runner, com cwd = checkout do repo. Commit/push como identidade do fleet.
"""

from __future__ import annotations

import asyncio


class SubprocessGit:
    def __init__(self, workdir: str) -> None:
        self._cwd = workdir

    async def _git(self, *args: str) -> int:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=self._cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode or 0

    async def prepare_branch(self, name: str) -> None:
        await self._git("checkout", "-B", name)

    async def commit_all(self, message: str) -> None:
        await self._git("add", "-A")
        # -c define identidade do bot; commit vazio é tolerado (ignora código de saída)
        await self._git(
            "-c", "user.email=fleet@roboto.dev", "-c", "user.name=roboto",
            "commit", "-m", message,
        )

    async def push(self, name: str) -> None:
        await self._git("push", "-u", "origin", name, "--force")
