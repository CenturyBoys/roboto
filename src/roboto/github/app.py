"""Cliente GitHub App (D17/D21): autentica como app -> token de instalação -> REST.

Controle fino do fluxo: permissões fine-grained, N repos por org, tokens curtos. Aqui só o
necessário para **materializar o IssueDraft numa issue** (fonte da verdade, D15/D20). Não é
exercitado no CI com credencial real; o caminho REST é testado via httpx.MockTransport injetando
um token (o JWT/troca de token precisa de chave privada real).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
import jwt

from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


@dataclass(frozen=True)
class IssueRef:
    repo: str
    number: int
    url: str


class GithubAppClient:
    def __init__(
        self,
        *,
        app_id: str,
        private_key: str,
        installation_id: str,
        api_base: str = "https://api.github.com",
        client: httpx.AsyncClient | None = None,
        token: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._installation_id = installation_id
        self._api = api_base.rstrip("/")
        self._client = client
        self._token = token  # injetável (teste/cache); se vazio, gera via JWT
        self._timeout = timeout

    async def create_issue(self, repo: str, title: str, body: str) -> Result[IssueRef, Error]:
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.post(
                f"{self._api}/repos/{repo}/issues",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"title": title, "body": body},
            )
            resp.raise_for_status()
            data = resp.json()
            return Ok(IssueRef(repo=repo, number=int(data["number"]), url=str(data["html_url"])))
        except httpx.HTTPError as exc:
            return Err(Error("github", f"create_issue {repo}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def open_pr(
        self, repo: str, *, title: str, body: str, head: str, base: str = "main"
    ) -> Result[IssueRef, Error]:
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.post(
                f"{self._api}/repos/{repo}/pulls",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"title": title, "body": body, "head": head, "base": base},
            )
            resp.raise_for_status()
            data = resp.json()
            return Ok(IssueRef(repo=repo, number=int(data["number"]), url=str(data["html_url"])))
        except httpx.HTTPError as exc:
            return Err(Error("github", f"open_pr {repo}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def get_pr(self, repo: str, number: int) -> Result[tuple[str, str], Error]:
        """(título, login do autor) do PR — p/ revisar PR de terceiros (reviewer≠autor)."""
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.get(
                f"{self._api}/repos/{repo}/pulls/{number}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            d = resp.json()
            return Ok((str(d.get("title", "")), str((d.get("user") or {}).get("login", ""))))
        except httpx.HTTPError as exc:
            return Err(Error("github", f"get_pr {repo}#{number}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def get_pr_diff(self, repo: str, number: int) -> Result[str, Error]:
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.get(
                f"{self._api}/repos/{repo}/pulls/{number}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3.diff",
                },
            )
            resp.raise_for_status()
            return Ok(resp.text)
        except httpx.HTTPError as exc:
            return Err(Error("github", f"get_pr_diff {repo}#{number}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def get_pr_head(self, repo: str, number: int) -> Result[str, Error]:
        """Branch head do PR — p/ CORRIGIR um PR já aberto no seu próprio branch (B)."""
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.get(
                f"{self._api}/repos/{repo}/pulls/{number}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            return Ok(str(((resp.json() or {}).get("head") or {}).get("ref", "")))
        except httpx.HTTPError as exc:
            return Err(Error("github", f"get_pr_head {repo}#{number}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]:
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.post(
                f"{self._api}/repos/{repo}/issues/{number}/comments",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"body": body},
            )
            resp.raise_for_status()
            return Ok(None)
        except httpx.HTTPError as exc:
            return Err(Error("github", f"comment_pr {repo}#{number}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def get_pr_comments(self, repo: str, number: int) -> Result[list[str], Error]:
        """Corpos dos comentários do PR — contexto p/ o re-review não repetir (#151)."""
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.get(
                f"{self._api}/repos/{repo}/issues/{number}/comments",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                params={"per_page": "30"},
            )
            resp.raise_for_status()
            return Ok([str(c.get("body", "")) for c in resp.json()])
        except httpx.HTTPError as exc:
            return Err(Error("github", f"get_pr_comments {repo}#{number}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def submit_review(
        self, repo: str, number: int, body: str, comments: list[tuple[str, int, str]]
    ) -> Result[None, Error]:
        """Posta um PR review (event=COMMENT, não bloqueia — merge é humano) com comentários INLINE
        por (path, line) + um corpo-resumo. Trilha D (review estruturado). Linhas fora do diff que o
        GitHub recusar caem no 422 — tratamos como falha suave no chamador."""
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        inline = [
            {"path": path, "line": line, "side": "RIGHT", "body": cbody}
            for (path, line, cbody) in comments
        ]
        try:
            token = await self._installation_token(client)
            resp = await client.post(
                f"{self._api}/repos/{repo}/pulls/{number}/reviews",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"event": "COMMENT", "body": body, "comments": inline},
            )
            resp.raise_for_status()
            return Ok(None)
        except httpx.HTTPError as exc:
            return Err(Error("github", f"submit_review {repo}#{number}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def list_recent_comments(
        self, repo: str
    ) -> Result[list[tuple[int, int, str]], Error]:
        """[(comment_id, issue_number, body)] dos comentários recentes (gatilho `@potter`, #166)."""
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.get(
                f"{self._api}/repos/{repo}/issues/comments",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                params={"sort": "created", "direction": "desc", "per_page": "30"},
            )
            resp.raise_for_status()
            out: list[tuple[int, int, str]] = []
            for c in resp.json():
                tail = str(c.get("issue_url", "")).rsplit("/", 1)[-1]
                if tail.isdigit():
                    out.append((int(c["id"]), int(tail), str(c.get("body", ""))))
            return Ok(out)
        except httpx.HTTPError as exc:
            return Err(Error("github", f"list_recent_comments {repo}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def checks_failed(self, repo: str, sha: str) -> Result[bool, Error]:
        """True se algum check-run do commit falhou (gatilho check_suite failed, #166)."""
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.get(
                f"{self._api}/repos/{repo}/commits/{sha}/check-runs",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            runs = resp.json().get("check_runs", [])
            return Ok(any(r.get("conclusion") in ("failure", "timed_out") for r in runs))
        except httpx.HTTPError as exc:
            return Err(Error("github", f"checks_failed {repo}@{sha}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def update_issue(
        self, repo: str, number: int, *, title: str, body: str
    ) -> Result[None, Error]:
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.patch(
                f"{self._api}/repos/{repo}/issues/{number}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"title": title, "body": body},
            )
            resp.raise_for_status()
            return Ok(None)
        except httpx.HTTPError as exc:
            return Err(Error("github", f"update_issue {repo}#{number}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def list_open_issues(
        self, repo: str, *, limit: int = 20
    ) -> Result[list[tuple[int, str]], Error]:
        """Lista issues abertas (nº, título), excluindo PRs. Contrato usado pelo Telegram."""
        rich = await self.list_open_issues_rich(repo, limit=limit)
        if isinstance(rich, Err):
            return rich
        return Ok([(n, t) for n, t, _ in rich.value])

    async def list_open_issues_rich(
        self, repo: str, *, limit: int = 20
    ) -> Result[list[tuple[int, str, list[str]]], Error]:
        """Issues abertas com labels (nº, título, labels), excluindo PRs. Para o cockpit (Fatia 6).

        Só `state=open` — issues `closed` NUNCA entram; PRs também são excluídos.
        """
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.get(
                f"{self._api}/repos/{repo}/issues",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                params={"state": "open", "per_page": limit},
            )
            resp.raise_for_status()
            items: list[tuple[int, str, list[str]]] = []
            for x in resp.json():
                if not isinstance(x, dict) or "pull_request" in x:  # exclui PRs
                    continue
                labels = [
                    str(lbl.get("name", ""))
                    for lbl in x.get("labels", [])
                    if isinstance(lbl, dict)
                ]
                items.append((int(x["number"]), str(x.get("title", "")), labels))
            return Ok(items)
        except httpx.HTTPError as exc:
            return Err(Error("github", f"list_open_issues {repo}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]:
        """Retorna (title, body) da issue — p/ o gate de prontidão antes de implementar (D28)."""
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.get(
                f"{self._api}/repos/{repo}/issues/{number}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return Ok((str(data.get("title", "")), str(data.get("body") or "")))
        except httpx.HTTPError as exc:
            return Err(Error("github", f"get_issue {repo}#{number}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def find_open_pr(self, repo: str, head_branch: str) -> Result[int | None, Error]:
        """Nº do PR aberto do branch, ou None. Idempotência contra PRs vivos (não duplica)."""
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            head = f"{repo.split('/')[0]}:{head_branch}"
            resp = await client.get(
                f"{self._api}/repos/{repo}/pulls",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                params={"head": head, "state": "open"},
            )
            resp.raise_for_status()
            data = resp.json()
            return Ok(int(data[0]["number"]) if data else None)
        except httpx.HTTPError as exc:
            return Err(Error("github", f"find_open_pr {repo} {head_branch}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def list_open_prs(self, repo: str) -> Result[list[tuple[int, str]], Error]:
        """(número, head_sha) dos PRs abertos — alimenta o gatilho por POLLING (Trilha B, #166)."""
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.get(
                f"{self._api}/repos/{repo}/pulls",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                params={"state": "open", "per_page": "50"},
            )
            resp.raise_for_status()
            out = [
                (int(p["number"]), str((p.get("head") or {}).get("sha", ""))) for p in resp.json()
            ]
            return Ok(out)
        except httpx.HTTPError as exc:
            return Err(Error("github", f"list_open_prs {repo}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def set_issue_state_label(
        self, repo: str, number: int, label: str
    ) -> Result[None, Error]:
        """Troca as labels `status:*` da issue pela `label` (preserva as demais) — projeção do
        estado canônico do daemon (Trilha A, #161). GitHub cria a label se ela não existir."""
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        hdr = {"Accept": "application/vnd.github+json"}
        try:
            token = await self._installation_token(client)
            hdr["Authorization"] = f"Bearer {token}"
            got = await client.get(
                f"{self._api}/repos/{repo}/issues/{number}/labels", headers=hdr
            )
            got.raise_for_status()
            current = [str(x["name"]) for x in got.json()]
            keep = [n for n in current if not n.startswith("status:")]
            if current == keep + [label]:
                return Ok(None)  # já está certo — não bate na API à toa
            resp = await client.put(
                f"{self._api}/repos/{repo}/issues/{number}/labels",
                headers=hdr,
                json={"labels": keep + [label]},
            )
            resp.raise_for_status()
            return Ok(None)
        except httpx.HTTPError as exc:
            return Err(Error("github", f"set_issue_state_label {repo}#{number}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def pr_merged(self, repo: str, number: int) -> Result[bool, Error]:
        """True se o PR foi MERGEADO (detecta o merge humano sem webhook — fecha o run local)."""
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.get(
                f"{self._api}/repos/{repo}/pulls/{number}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            return Ok(bool(resp.json().get("merged")))
        except httpx.HTTPError as exc:
            return Err(Error("github", f"pr_merged {repo} #{number}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def _installation_token(self, client: httpx.AsyncClient) -> str:
        if self._token:
            return self._token
        now = int(time.time())
        app_jwt = jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self._app_id},
            self._private_key,
            algorithm="RS256",
        )
        resp = await client.post(
            f"{self._api}/app/installations/{self._installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        self._token = str(resp.json()["token"])
        return self._token
