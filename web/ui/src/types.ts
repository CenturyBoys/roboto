// Espelha o JSON do console (src/roboto/web/console.py). Contrato estável = a API; a UI consome.

export interface Execution {
  id: number
  tenant: string
  repo: string
  issue_id: string
  agent: string
  state: string
  attempt: number
  created_at: string
  updated_at: string
}

export interface Session {
  id: number
  engine: string
  native_session_id: string | null
  state: string
}

export interface Interaction {
  id: number
  execution_id: number
  kind: string
  prompt: string
  options: string[]
  status: string
  answer: string | null
  answered_by: string | null
}

export interface LlmCall {
  run_id: number
  model: string
  tier: string
  tokens_in: number
  tokens_out: number
  cost_usd: number
  at: string
}

export interface Money {
  tokens: number
  cost_usd: number
}

export interface ExecutionDetail {
  execution: Execution
  sessions: Session[]
  interactions: Interaction[]
  cost: Money
}

export interface Costs {
  calls: LlmCall[]
  totals: Money
  by_execution: ({ run_id: number } & Money)[]
}

export interface PrDiff {
  number: number | null
  url: string | null
  diff: string
}

export interface Issue {
  number: number
  title: string
}

export interface IssueList {
  repo: string
  issues: Issue[]
  note?: string
  error?: string
}

export interface Terminal {
  terminal_url: string | null
  note?: string
}

export interface Health {
  ok: boolean
  mode: 'setup' | 'running'
}

export interface SetupStatus {
  configured: boolean
  missing: string[]
  present: string[]
}

export interface FeedEvent {
  id: number
  kind: 'message' | 'tool_call'
  text: string
  tool: string
  at: string
}
