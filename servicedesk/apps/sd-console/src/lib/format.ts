export function fmtClock(sec?: number | null): string {
  if (sec === undefined || sec === null || !isFinite(sec)) return '--:--';
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const mm = String(m).padStart(2, '0');
  const ss = String(r).padStart(2, '0');
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function fmtDateTime(iso?: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '-';
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' });
}

export function fmtNum(v?: number | null, digits = 0): string {
  if (v === undefined || v === null || !isFinite(v)) return '-';
  return v.toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtPct(ratio?: number | null, digits = 1): string {
  if (ratio === undefined || ratio === null || !isFinite(ratio)) return '-';
  return `${(ratio * 100).toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
}

export function scoreClass(score?: number | null): string {
  if (score === null || score === undefined) return '';
  if (score >= 80) return 'ok';
  if (score >= 60) return 'warn';
  return 'danger';
}

export const STATUS_LABEL: Record<string, string> = {
  observed: 'observado',
  not_observed: 'não observado',
  not_applicable: 'não aplicável',
};

export const ALERT_LABEL: Record<string, string> = {
  cliente_sem_solucao: 'Cliente sem solução',
  compromisso_retorno: 'Compromisso de retorno',
  reclamacao: 'Reclamação',
  pedido_supervisor: 'Pedido de supervisor',
  informacao_conflitante: 'Informação conflitante',
  quebra_procedimento: 'Quebra de procedimento',
  script_descumprido: 'Script obrigatório descumprido',
  recorrencia: 'Recorrência',
  oportunidade_base_conhecimento: 'Oportunidade de base de conhecimento',
};

export function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}
