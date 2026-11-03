"""Adapter de git por subprocess (IO real; não exercitado no CI). Implementa a porta GitOps.

Usado no container do runner, com cwd = checkout do repo. Commit/push como identidade do fleet.
"""

from __future__ import annotations

import asyncio


class GitError(RuntimeError):
    """Falha de um comando git que NÃO pode ser engolida (ex.: push) — o ciclo precisa saber."""


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

    async def _git_checked(self, *args: str) -> None:
        """Roda o git e LEVANTA GitError se falhar — não mascara a falha. Inclui stdout+stderr no
        motivo (hooks como pre-commit costumam imprimir no stdout)."""
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=self._cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if (proc.returncode or 0) != 0:
            saida = (err.decode(errors="replace") + out.decode(errors="replace")).strip()
            raise GitError(f"git {args[0]} falhou (code {proc.returncode}): {saida[:400]}")

    async def _git_out(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=self._cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        return out.decode(errors="replace") if (proc.returncode or 0) == 0 else ""

    async def prepare_branch(self, name: str) -> None:
        # checked: se o checkout falhar, commit/push iriam pra branch errada em silêncio
        await self._git_checked("checkout", "-B", name)

    async def checkout_remote(self, name: str) -> None:
        """Traz a branch REMOTA e entra NELA — p/ corrigir um PR já aberto (B). NÃO reseta p/ a
        base: o motor edita sobre o estado atual do PR. Sem isto, um `checkout -B` sobre um clone
        novo (em `develop`) + force-push SOBRESCREVERIA o PR. CHECKED: falha aqui é perigosa
        (force-push no alvo errado), então levanta em vez de seguir no estado errado."""
        await self._git_checked("fetch", "origin", name)
        await self._git_checked("checkout", "-B", name, f"origin/{name}")

    async def commit_all(self, message: str) -> None:
        await self._git_checked("add", "-A")  # add falho não pode ser engolido
        # "nada staged" (diff --cached --quiet == 0) é o ÚNICO caso tolerado — aí não há o que
        # commitar e a checagem de diff-vazio do ciclo decide. Se HÁ algo staged, o commit PRECISA
        # passar: um pre-commit hook que barra (prettier/lint/testes) agora LEVANTA com o motivo,
        # em vez de ficar staged-não-commitado e virar o enganoso "motor não editou nada".
        if await self._git("diff", "--cached", "--quiet") == 0:
            return
        await self._git_checked(
            "-c", "user.email=fleet@roboto.dev", "-c", "user.name=roboto",
            "commit", "-m", message,
        )

    async def push(self, name: str) -> None:
        # push NÃO pode falhar em silêncio: branch que não sobe vira 422 confuso no open_pr.
        await self._git_checked("push", "-u", "origin", name, "--force")

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

    async def revert_range(self, base: str, source_branch: str, revert_branch: str) -> bool:
        """Cria `revert_branch` a partir de origin/base e REVERTE os commits de `source_branch`
        (recuperação git-first, H). Retorna False se o revert falhar (ex.: conflito) — o chamador
        trata e NÃO empurra nada quebrado."""
        await self._git("fetch", "origin", base, source_branch)
        if await self._git("checkout", "-B", revert_branch, f"origin/{base}") != 0:
            return False
        code = await self._git(
            "-c", "user.email=fleet@roboto.dev", "-c", "user.name=roboto",
            "revert", "--no-edit", f"origin/{base}..origin/{source_branch}",
        )
        return code == 0
