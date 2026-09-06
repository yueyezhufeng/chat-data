import { useEffect, useState } from "react";
import { getJSON, type Snapshot, type StagedChange } from "../api";
import { ChangeCard, DualChart, OrdersTable } from "../cards";
import { Chat } from "../chat";

export function Ops({ go }: { go: (page: string) => void }) {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [recent, setRecent] = useState<any[]>([]);
  const [changes, setChanges] = useState<StagedChange[]>([]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await getJSON("/api/commerce/overview");
        if (!alive) return;
        setSnap(data.snapshot);
        setRecent(data.recent_orders);
        setChanges(data.recent_changes || []);
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 8000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const pending = changes.filter((c) => c.status === "staged");
  const applied = changes.find((c) => c.status === "applied" && c.impact?.after_ms != null);

  return (
    <div className="split-2">
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="tiles">
          <div className={`tile ${snap && !snap.db_healthy ? "alert" : ""}`}>
            <div className="label">今日订单</div>
            <div className="value num">{snap ? snap.orders_today.toLocaleString() : "—"}</div>
          </div>
          <div className="tile">
            <div className="label">今日销售额</div>
            <div className="value num">¥{snap ? snap.revenue_today.toLocaleString(undefined, { maximumFractionDigits: 0 }) : "—"}</div>
          </div>
          <div className="tile">
            <div className="label">转化率 <span className="pill muted">模拟推算</span></div>
            <div className="value num" style={{ color: "var(--violet)" }}>{snap ? snap.conversion_rate.toFixed(2) : "—"}<small> %</small></div>
          </div>
          <div className={`tile ${snap && !snap.db_healthy ? "alert" : "good"}`}>
            <div className="label">搜索 P99 · 数据库实测</div>
            <div className="value num">{snap ? snap.search_p99_ms : "—"}<small> ms</small></div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h3>延迟 × 转化率 · 近 12 小时</h3>
            <span className="hint">搜索延迟来自 search_log 实测；转化率按演示模型推算</span>
          </div>
          <div className="panel-body"><DualChart series={snap?.series || []} /></div>
        </div>

        {snap && !snap.db_healthy ? (
          <div className="panel" style={{ borderColor: "rgba(251,113,133,0.45)" }}>
            <div className="panel-body" style={{ display: "flex", alignItems: "center", gap: 14, padding: "15px 18px" }}>
              <span className="pill danger"><span className="dot pulse" />数据库延迟异常</span>
              <span style={{ fontSize: 13, color: "var(--ink-2)", flex: 1 }}>
                门店代理看到转化率回落，根源在数据库——右边让运营助手解读，或直接
                <a onClick={() => go("db")} style={{ cursor: "pointer" }}> 委托数据库诊疗代理 →</a>
              </span>
            </div>
          </div>
        ) : null}

        {applied ? (
          <div className="panel">
            <div className="panel-head"><h3>数据库侧已生效的优化</h3><span className="hint">业务波动回到正常的原因</span></div>
            <div className="panel-body"><ChangeCard change={applied} /></div>
          </div>
        ) : null}

        <div className="panel">
          <div className="panel-head"><h3>最新订单</h3><span className="hint">orders 表实时</span></div>
          <div className="panel-body"><OrdersTable items={recent} /></div>
        </div>

        {pending.length ? (
          <div className="panel" style={{ borderColor: "rgba(167,139,250,0.4)" }}>
            <div className="panel-head"><h3>待审批变更（{pending.length}）</h3></div>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {pending.map((c) => <ChangeCard key={c.change_id} change={c} />)}
            </div>
          </div>
        ) : null}
      </div>

      <div className="chat-panel panel">
        <div className="panel-head"><h3>运营助手</h3><span className="hint">门店代理 · 读权限</span></div>
        <Chat
          agent="commerce"
          height={560}
          starters={[
            "今天生意怎么样？",
            "转化率为什么掉了？",
            "搜索延迟高对生意有多大影响？",
            "看看最新的订单情况",
          ]}
        />
      </div>
    </div>
  );
}
