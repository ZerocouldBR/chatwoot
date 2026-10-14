/** Cliente da API de QA (qa-pipeline): /sd-qa/api/v1. Mesma sessão do sd-ops. */
import { http, qs, type Query } from './http';

export const SDQA = '/sd-qa/api/v1';

export type CritStatus = 'observed' | 'not_observed' | 'not_applicable';
export interface Criterion {
  key: string;
  label: string;
  weight: number;
  effective_weight: number;
  status: CritStatus;
  score: number | null;
  justification?: string | null;
  evidence_text?: string | null;
  evidence_start_s?: number | null;
  evidence_end_s?: number | null;
  evidence_verified?: boolean;
  confidence?: number | null;
  suggestion?: string | null;
  flags?: string[];
}
export interface Segment {
  idx: number;
  start_s: number;
  end_s: number;
  speaker?: string | null;
  channel?: number | null;
  text: string;
  confidence?: number | null;
  low_confidence?: boolean;
}
export interface EvalRow {
  id: number;
  recording_id: string;
  call_id?: string | null;
  ticket_id?: string | null;
  conversation_id?: string | null;
  agent_ref?: string | null;
  agent_name?: string | null;
  team?: string | null;
  status: string;
  review_state: 'pendente' | 'revisada' | 'contestada';
  ai_score: number | null;
  human_score: number | null;
  final_score: number | null;
  confidence?: number | null;
  llm_provider?: string;
  llm_model?: string;
  created_at: string;
  open_tasks: number;
}
export interface SummaryItem {
  texto: string;
  tipo: 'fato' | 'inferencia';
  evidencia: number[];
}
export interface Summary {
  id: number;
  status: 'draft' | 'approved' | 'edited' | 'rejected';
  content: Record<string, any>;
  final_content?: Record<string, any> | null;
  llm_provider: string;
  llm_model: string;
  reviewed_by?: string | null;
  note_status?: string;
}
export interface Task {
  id: number;
  kind: string;
  alert_type?: string | null;
  severity: string;
  title: string;
  detail?: string | null;
  evidence_text?: string | null;
  evidence_start_s?: number | null;
  evaluation_id?: number | null;
  recording_id?: string | null;
  agent_ref?: string | null;
  status: string;
  created_at: string;
}
export interface TranscriptionMeta {
  id: number;
  status: string;
  provider: string;
  model: string;
  language?: string;
  audio_duration_s?: number;
  coverage_ratio?: number;
  avg_confidence?: number;
  diarization?: string;
  pii_counts?: Record<string, number>;
  warnings?: string[];
  run: number;
}
export interface EvalDetail extends EvalRow {
  applicable_weight: number;
  redistribution: Record<string, any>;
  warnings: string[];
  criteria: Criterion[];
  stt_model?: string;
  human_reviews: { id: number; score: number | null; status: string; reviewer: string; comment?: string; created_at: string; criteria: Criterion[] }[];
  rubric: { id: number; code: string; version: number; name: string };
  prompt: { id: number; kind: string; version: string; sha256: string } | null;
  transcription: TranscriptionMeta;
  segments: Segment[];
  summary: Summary | null;
  tasks: Task[];
  events: { type: string; actor: string; role: string; payload: Record<string, any>; created_at: string }[];
  history: { id: number; score: number | null; status: string; is_current: boolean; llm_model?: string; rubric_version_id: number; prompt_version_id?: number; created_at: string }[];
}
export interface RecordingAnalysis {
  recording_id: string;
  call_id?: string;
  job: { id: number; run: number; status: string; stage?: string; error_code?: string | null; attempts: number; next_attempt_at?: string };
  transcription: TranscriptionMeta | null;
  segments: Segment[];
  summary: Summary | null;
  evaluation: (EvalRow & { criteria: Criterion[]; redistribution: Record<string, any> }) | null;
  alerts: Task[];
  csat: { score: number; scale_max: number; comment?: string | null; responded_at?: string } | null;
}
export interface Mark {
  id: number;
  start_s: number;
  end_s?: number | null;
  label: string;
  note?: string | null;
  created_by: string;
}

export const qaApi = {
  me: () => http<{ ref: string; name: string; tenant: string; roles: string[]; is_manager: boolean }>(`${SDQA}/me`),
  evaluations: (q: Query) => http<{ total: number; items: EvalRow[] }>(`${SDQA}/evaluations${qs(q)}`),
  evaluation: (id: number | string) => http<EvalDetail>(`${SDQA}/evaluations/${id}`),
  review: (id: number, body: unknown) => http<{ human_evaluation_id: number; score: number | null }>(`${SDQA}/evaluations/${id}/review`, { method: 'POST', json: body }),
  contest: (id: number, reason: string) => http(`${SDQA}/evaluations/${id}/contest`, { method: 'POST', json: { reason } }),
  resolveContest: (id: number, body: unknown) => http(`${SDQA}/evaluations/${id}/contest/resolve`, { method: 'POST', json: body }),
  recording: (rid: string) => http<RecordingAnalysis>(`${SDQA}/recordings/${encodeURIComponent(rid)}/analysis`),
  reprocess: (rid: string, mode: 'full' | 'analysis', reason: string) =>
    http<{ job_id: number; run: number; status: string }>(`${SDQA}/recordings/${encodeURIComponent(rid)}/reprocess`, { method: 'POST', json: { mode, reason } }),
  marks: (rid: string) => http<{ items: Mark[] }>(`${SDQA}/recordings/${encodeURIComponent(rid)}/marks`),
  addMark: (rid: string, body: { start_s: number; end_s?: number; label: string; note?: string }) =>
    http<{ id: number }>(`${SDQA}/recordings/${encodeURIComponent(rid)}/marks`, { method: 'POST', json: body }),
  access: (rid: string, action: string, detail: Record<string, unknown> = {}) =>
    http(`${SDQA}/access-log`, { method: 'POST', json: { recording_id: rid, action, detail } }),
  reviewSummary: (id: number, action: 'approve' | 'edit' | 'reject', content?: unknown) =>
    http<Summary>(`${SDQA}/summaries/${id}/review`, { method: 'POST', json: { action, content } }),
  tasks: (q: Query) => http<{ total: number; items: Task[] }>(`${SDQA}/review-tasks${qs(q)}`),
  patchTask: (id: number, body: unknown) => http<Task>(`${SDQA}/review-tasks/${id}`, { method: 'PATCH', json: body }),
  rubrics: () => http<{ items: any[] }>(`${SDQA}/rubrics`),
  activateRubric: (id: number) => http(`${SDQA}/rubrics/${id}/activate`, { method: 'POST' }),
  prompts: () => http<{ items: any[] }>(`${SDQA}/prompts`),
  quality: (q: Query) => http<Record<string, any>>(`${SDQA}/metrics/quality${qs(q)}`),
  agents: (q: Query) => http<{ items: any[] }>(`${SDQA}/agents/stats${qs(q)}`),
  csvUrl: (q: Query) => `${SDQA}/export/evaluations.csv${qs(q)}`,
};
