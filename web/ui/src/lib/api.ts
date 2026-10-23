import type {
  Costs,
  Execution,
  ExecutionDetail,
  Health,
  Interaction,
  IssueDetail,
  IssueList,
  PrDiff,
  RefineStep,
  SetupStatus,
  Terminal,
} from '@/types'

// O bearer do console (CONSOLE_TOKEN) vive no localStorage; toda chamada o injeta no header.
const TOKEN_KEY = 'rtok'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export class ApiError extends Error {
  constructor(public readonly status: number) {
    super(`HTTP ${status}`)
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { ...init?.headers, Authorization: `Bearer ${getToken()}` },
  })
  if (!res.ok) throw new ApiError(res.status)
  return (await res.json()) as T
}

export const listExecutions = () => api<{ executions: Execution[] }>('/executions')
export const getExecution = (id: number) => api<ExecutionDetail>(`/executions/${id}`)
export const getCosts = () => api<Costs>('/costs')
export const listIssues = () => api<IssueList>('/issues')
export const getIssue = (n: number) => api<IssueDetail>(`/issues/${n}`)
export const refineIssue = (n: number, transcript: [string, string][]) =>
  api<RefineStep>(`/issues/${n}/refine`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ transcript }),
  })
// Refino engine-scoped (Fatia 6/C): enfileira um run; o motor lê o repo e propõe. Devolve o run_id.
export const dispatchEngineRefine = (n: number) =>
  api<{ run_id: number }>(`/issues/${n}/refine-engine`, { method: 'POST' })
export const listInteractions = () => api<{ interactions: Interaction[] }>('/interactions')
export const answerInteraction = (id: number, answer: string) =>
  api<{ id: number; accepted: boolean; status: string }>(`/interactions/${id}/answer`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ answer }),
  })
export const getTerminal = (id: number) => api<Terminal>(`/executions/${id}/terminal`)
export const getPrDiff = (id: number) => api<PrDiff>(`/executions/${id}/diff`)

// Co-piloto (Fatia 5): manda mensagem pra sessão viva / interrompe. 409 = sessão não está viva.
export const steerExecution = (id: number, text: string) =>
  api<{ ok: boolean }>(`/executions/${id}/message`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text }),
  })
export const interruptExecution = (id: number) =>
  api<{ ok: boolean }>(`/executions/${id}/interrupt`, { method: 'POST' })
export const endExecution = (id: number) =>
  api<{ ok: boolean }>(`/executions/${id}/end`, { method: 'POST' })
// Aplicar a proposta do refino na issue do GitHub (D30: corpo editável, com OK do humano).
export const getProposal = (id: number) =>
  api<{ body: string; issue_id: string }>(`/executions/${id}/proposal`)
export const applyProposal = (id: number, body: string) =>
  api<{ ok: boolean; number: number }>(`/executions/${id}/apply`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ body }),
  })
export const cancelExecution = (id: number) =>
  api<{ id: number; state: string }>(`/executions/${id}/cancel`, { method: 'POST' })
export const retryExecution = (id: number) =>
  api<{ id: number; state: string }>(`/executions/${id}/retry`, { method: 'POST' })

// Setup mode (trilha O): o daemon serve /healthz com o modo; a tela de config usa status/save.
export const getHealth = () => api<Health>('/healthz')
export const getSetupStatus = () => api<SetupStatus>('/setup/status')
export const saveSetup = (values: Record<string, string>) =>
  api<SetupStatus & { saved: string[] }>('/setup', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ values }),
  })
