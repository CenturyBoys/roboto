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

    async def _git_out(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=self._cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        return out.decode(errors="replace") if (proc.returncode or 0) == 0 else ""

    async def prepare_branch(self, name: str) -> None:
        await self._git("checkout", "-B", name)

    async def checkout_remote(self, name: str) -> None:
        """Traz a branch REMOTA e entra NELA — p/ corrigir um PR já aberto (B). NÃO reseta p/ a
        base: o motor edita sobre o estado atual do PR. Sem isto, um `checkout -B` sobre um clone
        novo (em `develop`) + force-push SOBRESCREVERIA o PR."""
        await self._git("fetch", "origin", name)
        await self._git("checkout", "-B", name, f"origin/{name}")

    async def commit_all(self, message: str) -> None:
        await self._git("add", "-A")
        # -c define identidade do bot; commit vazio é tolerado (ignora código de saída)
        await self._git(
            "-c", "user.email=fleet@roboto.dev", "-c", "user.name=roboto",
            "commit", "-m", message,
        )

    async def push(self, name: str) -> None:
        await self._git("push", "-u", "origin", name, "--force")

    async def log_since(self, base: str) -> str:
        # mensagem COMPLETA (assunto+corpo) de cada commit da branch vs base — o motor escreve um
        # corpo explicativo, que vira a "história da implementação" no PR (não só o assunto).
        return await self._git_out(
            "log", f"origin/{base}..HEAD", "--no-merges", "--pretty=format:### %s%n%n%b"
        )

    async def changed_files(self, base: str) -> list[str]:
        """Arquivos alterados na branch vs a base (p/ o verify determinístico focar só neles)."""
        out = await self._git_out("diff", "--name-only", f"origin/{base}...HEAD")
        return [ln for ln in out.splitlines() if ln.strip()]

    async def show(self, ref: str, path: str) -> str:
        """Conteúdo do arquivo num ref (ex.: a base); "" se não existe lá (arquivo novo)."""
        return await self._git_out("show", f"{ref}:{path}")

    async def diff(self, base: str) -> str:
        """Diff unificado da branch vs a base — alimenta o secret-scan antes do push (H)."""
        return await self._git_out("diff", f"origin/{base}...HEAD")
