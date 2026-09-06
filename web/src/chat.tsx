import { useEffect, useRef, useState } from "react";
import { streamChat, startSession, TOOL_COPY, type AgentEvent, type StagedChange } from "./api";
import { PlanTree, ProductGrid, OrdersTable } from "./cards";

type Segment =
  | { kind: "text"; text: string }
  | { kind: "tool"; tool: string; status: string; summary: string }
  | { kind: "ui"; component: string; payload: any }
  | { kind: "error"; text: string };

type ChatItem = { role: "user" | "assistant"; segments?: Segment[]; text?: string };

export function Chat({
  agent,
  starters,
  onChangeUpdate,
  height,
}: {
  agent: string;
  starters: string[];
  onChangeUpdate?: (c: StagedChange) => void;
  height?: number;
}) {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("");
  const sessionRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [items, busy, status]);

  const send = async (text: string) => {
    if (busy || !text.trim()) return;
    setDraft("");
    setBusy(true);
    setItems((prev) => [...prev, { role: "user", text }]);
    setItems((prev) => [...prev, { role: "assistant", segments: [] }]);
    if (!sessionRef.current) sessionRef.current = await startSession(agent);
    const patchLast = (fn: (segs: Segment[]) => Segment[]) =>
      setItems((prev) => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        last.segments = fn(last.segments || []);
        return copy;
      });

    await streamChat(agent, sessionRef.current, text, (e: AgentEvent) => {
      if (e.type === "text_delta") {
        patchLast((segs) => {
          const lastText = segs[segs.length - 1];
          if (lastText && lastText.kind === "text") {
            return [...segs.slice(0, -1), { kind: "text", text: lastText.text + e.text }];
          }
          return [...segs, { kind: "text", text: e.text! }];
        });
      } else if (e.type === "tool_call") {
        setStatus(`${TOOL_COPY[e.tool || ""] || e.tool}${e.label ? ` · ${e.label}` : ""}…`);
        patchLast((segs) => [...segs, { kind: "tool", tool: e.tool!, status: "running", summary: "" }]);
      } else if (e.type === "tool_result") {
        setStatus("");
        patchLast((segs) =>
          segs.map((s) => (s.kind === "tool" && s.status === "running" ? { ...s, status: e.status!, summary: e.summary || "" } : s))
        );
      } else if (e.type === "ui") {
        patchLast((segs) => [...segs, { kind: "ui", component: e.component!, payload: e.payload }]);
      } else if (e.type === "change_update" && e.change) {
        onChangeUpdate?.(e.change);
      } else if (e.type === "error") {
        patchLast((segs) => [...segs, { kind: "error", text: e.message! }]);
      }
    });
    setStatus("");
    setBusy(false);
  };

  const renderSegment = (s: Segment, i: number) => {
    if (s.kind === "text") return <div className="ai-text" key={i}>{s.text}</div>;
    if (s.kind === "error") return <div className="ai-text" key={i} style={{ color: "var(--danger)" }}>⚠ {s.text}</div>;
    if (s.kind === "tool") {
      const mark = s.status === "running" ? "◌" : s.status === "blocked" ? "⊘" : s.status === "error" ? "✕" : "✓";
      return (
        <div className={`tool-line ${s.status}`} key={i}>
          <span className="tick">{mark}</span>
          <span>{TOOL_COPY[s.tool] || s.tool}</span>
          {s.status === "blocked" ? <span style={{ color: "var(--warn)" }}>· 被门控拦截</span> : null}
          {s.status === "running" && !busy ? null : null}
        </div>
      );
    }
    if (s.kind === "ui") {
      if (s.component === "plan_tree") return <PlanTree key={i} sql={s.payload.sql} tree={s.payload.tree} />;
      if (s.component === "products") return <ProductsCard key={i} payload={s.payload} />;
      if (s.component === "orders") return <OrdersCard key={i} payload={s.payload} />;
      return null;
    }
    return null;
  };

  return (
    <div className="chat panel" style={height ? { height } : undefined}>
      <div className="chat-scroll" ref={scrollRef}>
        {items.length === 0 ? (
          <>
            <p style={{ color: "var(--ink-2)", fontSize: 13.5, margin: "4px 2px 10px" }}>
              所有数据来自真实数据库；所有写操作都要经人批准。试试：
            </p>
            <div className="starters">
              {starters.map((s) => (
                <button className="starter" key={s} onClick={() => send(s)} disabled={busy}>{s}</button>
              ))}
            </div>
          </>
        ) : (
          items.map((item, i) =>
            item.role === "user" ? (
              <div className="msg-user" key={i}>{item.text}</div>
            ) : (
              <div className="msg-ai" key={i}>{(item.segments || []).map(renderSegment)}</div>
            )
          )
        )}
        {busy ? (
          <div className="working"><span className="bar" />{status || "正在思考…"}</div>
        ) : null}
      </div>
      <div className="composer">
        <textarea
          value={draft}
          placeholder={busy ? "正在处理…" : "问点什么…（Enter 发送）"}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(draft);
            }
          }}
        />
        <button className="send" disabled={busy || !draft.trim()} onClick={() => send(draft)}>↑</button>
      </div>
    </div>
  );
}

function ProductsCard({ payload }: { payload: any }) {
  return (
    <div className="card">
      <div className="card-head">
        <span className="t">搜索结果</span>
        <span className="m">门店数据库实测 · {payload.elapsed_ms} ms</span>
        <span className={`lat-badge ${payload.elapsed_ms > 300 ? "slow" : payload.elapsed_ms > 80 ? "" : "fast"}`}>
          {payload.elapsed_ms} ms
        </span>
      </div>
      <div className="card-body"><ProductGrid items={payload.items} /></div>
    </div>
  );
}

function OrdersCard({ payload }: { payload: any }) {
  return (
    <div className="card">
      <div className="card-head">
        <span className="t">最近订单</span>
        <span className={`lat-badge ${payload.elapsed_ms > 300 ? "slow" : payload.elapsed_ms > 80 ? "" : "fast"}`}>
          查询耗时 {payload.elapsed_ms} ms
        </span>
      </div>
      <div className="card-body"><OrdersTable items={payload.items} /></div>
    </div>
  );
}
