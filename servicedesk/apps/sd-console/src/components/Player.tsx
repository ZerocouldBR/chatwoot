/**
 * Player de gravação (Módulo 4): play/pause, progresso, duração, velocidade, navegação sincronizada pela
 * transcrição, marcação de trechos e registro de acesso. A URL vem do sd-ops (token HMAC de 300 s,
 * auditado lá); o player registra play/velocidade/marcação no qa-pipeline. Sem botão de download.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { errorText } from '../lib/http';
import { fmtClock } from '../lib/format';
import { qaApi, type Mark, type Segment } from '../lib/qa';
import * as sdops from '../lib/sdops';
import { ErrorBox, Notice } from './ui';

const RATES = [0.75, 1, 1.25, 1.5, 2];

export interface PlayerProps {
  recordingId: string;
  segments: Segment[];
  seekTo?: { t: number; n: number } | null;
  allowMarks?: boolean;
}

export function Player({ recordingId, segments, seekTo, allowMarks = true }: PlayerProps) {
  const audio = useRef<HTMLAudioElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<number>(0);
  const [error, setError] = useState('');
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRate] = useState(1);
  const [marks, setMarks] = useState<Mark[]>([]);
  const [markLabel, setMarkLabel] = useState('');
  const logged = useRef(false);
  const list = useRef<HTMLDivElement>(null);

  const loadUrl = useCallback(async () => {
    setError('');
    try {
      const r = await sdops.recordingUrl(recordingId);
      setSrc(r.url);
      setExpiresAt(Date.now() + (r.expires_in ?? 300) * 1000);
    } catch (e) {
      setError(`Gravação indisponível: ${errorText(e)}`);
    }
  }, [recordingId]);

  useEffect(() => {
    setSrc(null);
    logged.current = false;
    loadUrl();
    qaApi.marks(recordingId).then((r) => setMarks(r.items)).catch(() => setMarks([]));
  }, [recordingId, loadUrl]);

  useEffect(() => {
    if (seekTo && audio.current) {
      audio.current.currentTime = seekTo.t;
      setTime(seekTo.t);
    }
  }, [seekTo]);

  const current = useMemo(() => segments.findIndex((s) => time >= s.start_s && time < s.end_s + 0.25), [segments, time]);

  useEffect(() => {
    if (current < 0 || !list.current) return;
    // Rola só a caixa da transcrição (scrollIntoView rolaria também a página/iframe inteira).
    const box = list.current;
    const el = box.querySelector<HTMLElement>(`[data-idx="${segments[current]?.idx}"]`);
    if (el && (el.offsetTop < box.scrollTop || el.offsetTop + el.offsetHeight > box.scrollTop + box.clientHeight)) {
      box.scrollTop = Math.max(0, el.offsetTop - box.clientHeight / 3);
    }
  }, [current, segments]);

  async function toggle() {
    const a = audio.current;
    if (!a || !src) return;
    if (a.paused) {
      if (Date.now() > expiresAt - 5000) await loadUrl(); // URL temporária vencida: pede outra
      try {
        await a.play();
      } catch {
        setError('O navegador não conseguiu reproduzir o áudio.');
        return;
      }
      if (!logged.current) {
        logged.current = true;
        qaApi.access(recordingId, 'play', { position_s: Math.round(a.currentTime), rate }).catch(() => undefined);
      }
    } else a.pause();
  }

  function seek(t: number) {
    if (audio.current) audio.current.currentTime = t;
    setTime(t);
  }

  function changeRate(r: number) {
    setRate(r);
    if (audio.current) audio.current.playbackRate = r;
    qaApi.access(recordingId, 'rate', { rate: r }).catch(() => undefined);
  }

  async function addMark() {
    const label = markLabel.trim() || 'trecho';
    try {
      const r = await qaApi.addMark(recordingId, { start_s: Math.round(time * 10) / 10, label });
      setMarks((m) => [...m, { id: r.id, start_s: time, label, created_by: 'você' }].sort((a, b) => a.start_s - b.start_s));
      setMarkLabel('');
    } catch (e) {
      setError(`Não foi possível marcar: ${errorText(e)}`);
    }
  }

  return (
    <section className="player" aria-label="Gravação da ligação">
      {error ? <ErrorBox error={error} onRetry={loadUrl} /> : null}
      {src ? (
        <audio
          ref={audio}
          src={src}
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
          onError={() => setError('Falha ao carregar o áudio (a URL temporária pode ter expirado).')}
          controlsList="nodownload"
        />
      ) : null}
      <div className="controls">
        <button className="primary" onClick={toggle} disabled={!src} aria-label={playing ? 'Pausar' : 'Reproduzir'}>
          {playing ? '❚❚ Pausar' : '▶ Ouvir'}
        </button>
        <span className="mono small" aria-live="off">
          {fmtClock(time)} / {fmtClock(duration || segments[segments.length - 1]?.end_s)}
        </span>
        <input
          type="range"
          min={0}
          max={duration || segments[segments.length - 1]?.end_s || 0}
          step={0.1}
          value={time}
          onChange={(e) => seek(Number(e.target.value))}
          aria-label="Posição na gravação"
          disabled={!src}
        />
        <label className="row" style={{ flexDirection: 'row', alignItems: 'center' }}>
          <span className="sr-only">Velocidade</span>
          <select value={rate} onChange={(e) => changeRate(Number(e.target.value))} aria-label="Velocidade de reprodução">
            {RATES.map((r) => (
              <option key={r} value={r}>
                {r.toLocaleString('pt-BR')}x
              </option>
            ))}
          </select>
        </label>
      </div>
      {allowMarks ? (
        <div className="row">
          <input
            placeholder="Rótulo do trecho (ex.: confirmação de dados)"
            value={markLabel}
            onChange={(e) => setMarkLabel(e.target.value)}
            aria-label="Rótulo da marcação"
            maxLength={64}
            style={{ flex: 1 }}
          />
          <button onClick={addMark}>Marcar {fmtClock(time)}</button>
        </div>
      ) : null}
      {marks.length ? (
        <div className="marks" aria-label="Trechos marcados">
          {marks.map((m) => (
            <button key={m.id} className="badge info" style={{ height: 24 }} onClick={() => seek(m.start_s)}>
              {fmtClock(m.start_s)} {m.label}
            </button>
          ))}
        </div>
      ) : null}
      {segments.length ? (
        <div className="transcript" ref={list} role="list" aria-label="Transcrição (clique para ir ao trecho)">
          {segments.map((s, i) => (
            <button
              key={s.idx}
              data-idx={s.idx}
              role="listitem"
              className={`seg${i === current ? ' current' : ''}${s.low_confidence ? ' low' : ''}`}
              aria-current={i === current ? 'true' : undefined}
              onClick={() => seek(s.start_s)}
              title={s.low_confidence ? 'Baixa confiança do reconhecimento de voz' : undefined}
            >
              <span className="ts">{fmtClock(s.start_s)}</span>
              <span className="who">{s.speaker || (s.channel !== null && s.channel !== undefined ? `canal ${s.channel + 1}` : '')}</span>
              <span>{s.text}</span>
            </button>
          ))}
        </div>
      ) : (
        <Notice kind="plain">Transcrição ainda não disponível.</Notice>
      )}
    </section>
  );
}
