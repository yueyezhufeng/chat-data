import { useState } from "react";
import type { StagedChange, SlowQuery, Product, Bucket } from "./api";
import { postJSON } from "./api";

/* ---------- 执行计划树 ---------- */

type PlanNode = { depth: number; label: string };

function parseTree(tree: string): PlanNode[] {
  return tree.split("\n").filter((l) => l.trim()).map((line) => {
    const depth = Math.floor((line.length - line.trimStart().length) / 4);
    return { depth, label: line.trim().replace(/^->\s*/, "") };
  });
}

function planBadge(label: string): { text: string; cls: string } | null {
  if (/table scan/i.test(label)) return { text: "全表扫描", cls: "scan" };
  if (/index range|index lookup|covering index|index scan/i.test(label)) return { text: "索引", cls: "index" };
  if (/sort/i.test(label)) return { text: "排序", cls: "sort" };
  if (/filter/i.test(label)) return { text: "过滤", cls: "filter" };
  return null;
}

export function PlanTree({ sql, tree }: { sql: string; tree: string }) {
  const nodes = parseTree(tree);
  return (
    <div className="card">
      <div className="card-head">
        <span className="t">执行计划</span>
        <span className="m">EXPLAIN FORMAT=TREE · 服务端生成，模型只读</span>
      </div>
      <div className="card-body">
        <div className="sql-chip">{sql}</div>
        <div className="tree">
          {nodes.map((n, i) => {
            const badge = planBadge(n.label);
            return (
              <div className="node" key={i} style={{ paddingLeft: n.depth * 22 }}>
                {badge ? <span className={`badge ${badge.cls}`}>{badge.text}</span> : null}
                <span style={{ color: badge?.cls === "scan" ? "#fb7185" : undefined }}>{n.label}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ---------- 慢查询榜 ---------- */

export function SlowQueryList({ items, compact = false }: { items: SlowQuery[]; compact?: boolean }) {
  if (!items.length) return <p style={{ color: "var(--ink-soft)", fontSize: 13 }}>暂无慢查询记录。</p>;
  const max = Math.max(...items.map((i) => i.avg_ms), 1);
  return (
    <div>
      {items.slice(0, compact ? 3 : 8).map((q, i) => (
        <div className="slow-row" key={i}>
          <div className="rank">{i + 1}</div>
          <div className="sql">
            <div className="t" title={q.sample_text}>{q.sample_text}</div>
            <div className="s num">
              {q.count_star} 次 · 平均扫描 {q.rows_examined.toLocaleString()} 行 · 累计 {q.total_sec}s
              <div className="msbar"><i style={{ width: `${Math.max(4, (q.avg_ms / max) * 100)}%` }} /></div>
            </div>
          </div>
          <div className="ms">
            <b className="num" style={{ color: q.avg_ms > 100 ? "var(--danger)" : q.avg_ms > 20 ? "var(--warn)" : "var(--ok)" }}>{q.avg_ms}</b>
            <div className="u">ms 平均</div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- 变更卡片（暂存/批准/驳回） ---------- */

export function ChangeCard({ change, onUpdate }: { change: StagedChange; onUpdate?: (c: StagedChange) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = async (action: "apply" | "discard") => {
    setBusy(true);
    setError(null);
    try {
      const body = action === "apply" ? { approved_by: "DBA" } : { by: "DBA" };
      const data = await postJSON<{ change: StagedChange }>(`/api/changes/${change.change_id}/${action}`, body);
      onUpdate?.(data.change);
    } catch (e: any) {
      setError(String(e.message || e).slice(0, 120));
    }
    setBusy(false);
  };
  const impact = change.impact || {};
  const before = impact.before_ms, after = impact.after_ms;
  return (
    <div className="card">
      <div className="card-head">
        <span className="t">{change.summary}</span>
        <span className="pill muted num">{change.change_id}</span>
        <span className={`chg-status pill ${change.status === "staged" ? "violet" : change.status === "applied" ? "ok" : "muted"}`}>
          <span className="dot" />{change.status === "staged" ? "待批准" : change.status === "applied" ? "已批准" : "已驳回"}
        </span>
      </div>
      <div className="card-body">
        <div className="sql-chip chg-sql">{change.sql}</div>
        {impact.rationale ? <div style={{ fontSize: 12.5, color: "var(--ink-2)" }}>理由：{impact.rationale}</div> : null}
        {change.status === "applied" && before != null ? (
          <div className="chg-impact">
            <span className="num" style={{ fontSize: 15, color: "var(--danger)", textDecoration: "line-through" }}>{before} ms</span>
            <span style={{ color: "var(--ink-faint)" }}>→</span>
            <span className="n num">{after ?? "?"} ms</span>
            <span className="d">
              实测「整改前 → 整改后」，同一条查询，同一把尺子
              {after ? <>，提升 <b style={{ color: "var(--ok)" }}>{(before / after).toFixed(0)} 倍</b></> : null}
            </span>
          </div>
        ) : null}
        {change.status === "staged" ? (
          <div className="chg-actions">
            <button className="btn approve sm" disabled={busy} onClick={() => act("apply")}>✓ 批准执行</button>
            <button className="btn reject sm" disabled={busy} onClick={() => act("discard")}>驳回</button>
            <span className="note">批准前数据库不会发生任何变化；聊天里说"同意"无效</span>
          </div>
        ) : (
          <div style={{ marginTop: 9, fontSize: 12, color: "var(--ink-soft)" }}>
            {change.status === "applied"
              ? <>由 {change.applied_by} 于 {change.applied_at} 批准执行</>
              : <>已驳回，未做任何更改</>}
          </div>
        )}
        {error ? <div style={{ color: "var(--danger)", fontSize: 12.5, marginTop: 6 }}>{error}</div> : null}
      </div>
    </div>
  );
}

/* ---------- 商品 / 订单 ---------- */

export function ProductGrid({ items }: { items: Product[] }) {
  if (!items.length) return null;
  return (
    <div className="prod-grid">
      {items.map((p) => (
        <div className="prod" key={p.id}>
          <div className="nm">{p.name}</div>
          <div className="cat">{p.category}</div>
          <div className="meta">
            <span className="price num">¥{p.price}</span>
            <span className={`stk num ${p.stock === 0 ? "zero" : ""}`}>{p.stock === 0 ? "缺货" : `库存 ${p.stock}`}</span>
          </div>
          <div style={{ fontSize: 10.5, color: "var(--ink-faint)", marginTop: 4 }}>近30天售 {p.sales_30d} · ID {p.id}</div>
        </div>
      ))}
    </div>
  );
}

export function OrdersTable({ items }: { items: any[] }) {
  if (!items.length) return null;
  const statusPill: Record<string, string> = {
    delivered: "ok", shipped: "info", processing: "warn", cancelled: "muted",
  };
  const statusText: Record<string, string> = {
    delivered: "已送达", shipped: "配送中", processing: "处理中", cancelled: "已取消",
  };
  return (
    <table className="tbl">
      <thead><tr><th>订单</th><th>金额</th><th>状态</th><th>渠道</th><th>时间</th></tr></thead>
      <tbody>
        {items.map((o) => (
          <tr key={o.id}>
            <td className="num">#{o.id}</td>
            <td className="num">¥{o.total}</td>
            <td><span className={`pill ${statusPill[o.status] || "muted"}`}>{statusText[o.status] || o.status}</span></td>
            <td style={{ color: "var(--ink-soft)" }}>{o.channel}</td>
            <td className="num" style={{ color: "var(--ink-soft)" }}>{o.created_at?.slice(5, 16)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ---------- 双轴联动大图：延迟 vs 转化率 ---------- */

export function DualChart({ series }: { series: Bucket[] }) {
  if (!series.length) return null;
  const W = 860, H = 260, padL = 46, padR = 46, padT = 18, padB = 34;
  const iw = W - padL - padR, ih = H - padT - padB;
  const maxLat = Math.max(...series.map((s) => s.max_ms), 100) * 1.15;
  const x = (i: number) => padL + (series.length === 1 ? iw / 2 : (i / (series.length - 1)) * iw);
  const yLat = (v: number) => padT + ih - (v / maxLat) * ih;
  const yConv = (v: number) => padT + ih - (v / 4) * ih;   // conversion axis fixed 0-4%
  const latPath = series.map((s, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${yLat(s.max_ms).toFixed(1)}`).join(" ");
  const convPath = series.map((s, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${yConv(s.conversion).toFixed(1)}`).join(" ");
  const area = `${latPath} L${x(series.length - 1).toFixed(1)},${padT + ih} L${padL},${padT + ih} Z`;
  const peak = series.reduce((a, b) => (b.max_ms > a.max_ms ? b : a), series[0]);
  const peakIdx = series.indexOf(peak);
  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`}>
        <defs>
          <linearGradient id="latArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2dd4ff" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#2dd4ff" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line x1={padL} x2={W - padR} y1={padT + ih * f} y2={padT + ih * f} stroke="rgba(148,163,255,0.08)" />
            <text x={padL - 8} y={padT + ih * f + 4} textAnchor="end" fontSize="10" fill="#7e89ab" fontFamily="var(--mono)">
              {Math.round(maxLat * (1 - f))}
            </text>
            <text x={W - padR + 8} y={padT + ih * f + 4} fontSize="10" fill="#a78bfa" fontFamily="var(--mono)">
              {(4 * (1 - f)).toFixed(1)}%
            </text>
          </g>
        ))}
        <path d={area} fill="url(#latArea)" />
        <path d={latPath} fill="none" stroke="#2dd4ff" strokeWidth="2.2" strokeLinejoin="round" />
        <path d={convPath} fill="none" stroke="#a78bfa" strokeWidth="2" strokeDasharray="5 4" />
        {series.map((s, i) => (
          <circle key={i} cx={x(i)} cy={yConv(s.conversion)} r="2.6" fill="#a78bfa" />
        ))}
        <g>
          <line x1={x(peakIdx)} x2={x(peakIdx)} y1={padT} y2={padT + ih} stroke="rgba(251,113,133,0.5)" strokeDasharray="4 4" />
          <text x={x(peakIdx)} y={padT - 4} textAnchor="middle" fontSize="10.5" fill="#fb7185">
            延迟峰值 {peak.max_ms}ms
          </text>
        </g>
        {series.map((s, i) =>
          i % Math.ceil(series.length / 8) === 0 ? (
            <text key={i} x={x(i)} y={H - 10} textAnchor="middle" fontSize="10" fill="#7e89ab">{s.bucket}</text>
          ) : null
        )}
      </svg>
      <div className="legend">
        <span><i style={{ background: "#2dd4ff" }} />门店查询延迟 ms（实线/面积，左轴）</span>
        <span><i style={{ background: "#a78bfa" }} />下单转化率 %（虚线，右轴，模拟推算）</span>
      </div>
    </div>
  );
}
