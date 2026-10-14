/**
 * Gráficos SVG leves, uma série por gráfico (sem legenda: o título nomeia a série), marcas finas com
 * ponta arredondada, grade recessiva, tooltip por marca e tabela equivalente para leitores de tela.
 */
import { useId, useState } from 'react';

interface Datum {
  label: string;
  value: number | null;
}

const tick = (v: number) => (Number.isInteger(v) ? String(v) : v.toLocaleString('pt-BR', { maximumFractionDigits: 1 }));

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

function SrTable({ data, unit, caption }: { data: Datum[]; unit?: string; caption: string }) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <tbody>
        {data.map((d) => (
          <tr key={d.label}>
            <th scope="row">{d.label}</th>
            <td>
              {d.value ?? '-'}
              {unit || ''}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function BarChart({ data, title, unit = '', height = 160 }: { data: Datum[]; title: string; unit?: string; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const id = useId();
  const W = 480;
  const pad = { l: 32, r: 8, t: 8, b: 24 };
  const max = niceMax(Math.max(0, ...data.map((d) => d.value || 0)));
  const bw = (W - pad.l - pad.r) / Math.max(1, data.length);
  const barW = Math.min(36, bw * 0.6);
  const y = (v: number) => pad.t + (height - pad.t - pad.b) * (1 - v / max);
  return (
    <figure className="chart" style={{ position: 'relative', margin: 0 }} aria-labelledby={id}>
      <figcaption id={id} className="sr-only">
        {title}
      </figcaption>
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={title}>
        <g className="grid">
          {[0, 0.5, 1].map((f) => (
            <line key={f} x1={pad.l} x2={W - pad.r} y1={y(max * f)} y2={y(max * f)} strokeWidth={1} />
          ))}
        </g>
        <g className="axis">
          {[0, 0.5, 1].map((f) => (
            <text key={f} x={pad.l - 6} y={y(max * f) + 4} textAnchor="end">
              {tick(max * f)}
            </text>
          ))}
          {data.map((d, i) => (
            <text key={d.label} x={pad.l + bw * i + bw / 2} y={height - 6} textAnchor="middle">
              {d.label}
            </text>
          ))}
        </g>
        {data.map((d, i) => {
          const v = d.value || 0;
          const x = pad.l + bw * i + (bw - barW) / 2;
          const top = y(v);
          const h = Math.max(0, y(0) - top);
          const r = Math.min(4, h / 2, barW / 2);
          const path = h
            ? `M${x},${y(0)} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${y(0)} Z`
            : '';
          return (
            <g key={d.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={pad.l + bw * i} y={pad.t} width={bw} height={height - pad.t - pad.b} fill="transparent" />
              {path ? <path d={path} fill="var(--sd-chart)" opacity={hover === null || hover === i ? 1 : 0.55} /> : null}
            </g>
          );
        })}
      </svg>
      {hover !== null ? (
        <div className="tooltip" style={{ left: `${((pad.l + bw * hover + bw / 2) / W) * 100}%`, top: 0, transform: 'translateX(-50%)' }}>
          <strong>{data[hover].label}</strong>: {data[hover].value ?? '-'}
          {unit}
        </div>
      ) : null}
      <SrTable data={data} unit={unit} caption={title} />
    </figure>
  );
}

export function LineChart({ data, title, unit = '', height = 160, yMax }: { data: Datum[]; title: string; unit?: string; height?: number; yMax?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const id = useId();
  const W = 480;
  const pad = { l: 32, r: 12, t: 10, b: 24 };
  const vals = data.map((d) => d.value).filter((v): v is number => v !== null);
  const max = yMax ?? niceMax(Math.max(1, ...vals));
  const n = Math.max(1, data.length - 1);
  const x = (i: number) => pad.l + ((W - pad.l - pad.r) * i) / n;
  const y = (v: number) => pad.t + (height - pad.t - pad.b) * (1 - v / max);
  const pts = data.map((d, i) => (d.value === null ? null : [x(i), y(d.value)] as const));
  const path = pts.reduce((acc, p, i) => (p ? acc + `${acc && pts[i - 1] ? 'L' : 'M'}${p[0]},${p[1]} ` : acc), '');
  const step = Math.ceil(data.length / 6);
  return (
    <figure className="chart" style={{ position: 'relative', margin: 0 }} aria-labelledby={id}>
      <figcaption id={id} className="sr-only">
        {title}
      </figcaption>
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={title} onMouseLeave={() => setHover(null)}>
        <g className="grid">
          {[0, 0.5, 1].map((f) => (
            <line key={f} x1={pad.l} x2={W - pad.r} y1={y(max * f)} y2={y(max * f)} strokeWidth={1} />
          ))}
        </g>
        <g className="axis">
          {[0, 0.5, 1].map((f) => (
            <text key={f} x={pad.l - 6} y={y(max * f) + 4} textAnchor="end">
              {tick(max * f)}
            </text>
          ))}
          {data.map((d, i) =>
            i % step === 0 ? (
              <text key={d.label} x={x(i)} y={height - 6} textAnchor="middle">
                {d.label}
              </text>
            ) : null,
          )}
        </g>
        <path d={path} fill="none" stroke="var(--sd-chart)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {pts.map((p, i) =>
          p ? (
            <g key={i}>
              <rect x={x(i) - (W / Math.max(2, data.length)) / 2} y={pad.t} width={W / Math.max(2, data.length)} height={height - pad.t - pad.b} fill="transparent" onMouseEnter={() => setHover(i)} />
              {hover === i ? <line x1={p[0]} x2={p[0]} y1={pad.t} y2={y(0)} stroke="var(--sd-border)" /> : null}
              <circle cx={p[0]} cy={p[1]} r={hover === i ? 5 : 4} fill="var(--sd-chart)" stroke="var(--sd-surface)" strokeWidth={2} />
            </g>
          ) : null,
        )}
      </svg>
      {hover !== null ? (
        <div className="tooltip" style={{ left: `${(x(hover) / W) * 100}%`, top: 0, transform: 'translateX(-50%)' }}>
          <strong>{data[hover].label}</strong>: {data[hover].value ?? '-'}
          {unit}
        </div>
      ) : null}
      <SrTable data={data} unit={unit} caption={title} />
    </figure>
  );
}
