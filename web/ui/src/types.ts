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

export interface ToolUsage {
  total: number
  by_category: Record<string, number>
  efficiency: number | null
}

export interface Risk {
  level: 'baixo' | 'medio' | 'alto'
  reasons: string[]
}

export interface ExecutionDetail {
  execution: Execution
  sessions: Session[]
  interactions: Interaction[]
  cost: Money
  tool_usage: ToolUsage
  risk: Risk
  live: boolean
  secret_blocked?: boolean // run falhou barrado pelo secret-scan → oferece override humano
}

export interface Budget {
  spent_usd: number
  cap_usd: number
  pct: number
  alert: boolean
  over: boolean
  month_start: string
}

export interface Costs {
  calls: LlmCall[]
  totals: Money
  by_execution: ({ run_id: number } & Money)[]
  budget: Budget
}

export interface Overview {
  by_state: Record<string, number>
  total: number
  active: number
  wip_limit: number
  queued: number
  waiting: number
  failed: number
  done: number
  dead_letters: number
  budget: Budget
}

export interface PrDiff {
  number: number | null
  url: string | null
  diff: string
}

export interface Issue {
  number: number
  title: string
  labels: string[]
}

export interface IssueList {
  repo: string
  issues: Issue[]
  note?: string
  error?: string
}

export interface Dor {
  ready: boolean
  missing: string[]
}

export interface IssueDetail {
  number: number
  title: string
  body: string
  dor: Dor
}

export interface RefineStep {
  question: string | null
  draft: { title: string; body: string } | null
  dor?: Dor
}

// Breakdown de épico (#203): item esqueleto proposto + resposta dos endpoints.
export interface BreakdownItem {
  title: string
  points: string[]
  depends_on_prev: boolean
}

export interface BreakdownStep {
  question: string | null
  items: BreakdownItem[] | null
}

export interface CreatedSubIssue {
  number: number
  url: string
  title: string
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
  kind: 'message' | 'tool_call' | 'user'
  text: string
  tool: string
  at: string
}
