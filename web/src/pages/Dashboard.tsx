import { useEffect, useState } from "react";
import { getJSON, type Snapshot, type SlowQuery, type StagedChange } from "../api";
import { ChangeCard, DualChart, SlowQueryList } from "../cards";

export function Dashboard({ go }: { go: (page: string) => void }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [slow, setSlow] = useState<SlowQuery[]>([]);
  const [changes, setChanges] = useState<StagedChange[]>([]);
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [c, m, h, ch] = await Promise.all([
          getJSON("/api/commerce/overview"),
          getJSON("/api/mysql/overview"),
          getJSON("/api/health"),
          getJSON("/api/changes"),
        ]);
        if (!alive) return;
        setSnapshot(c.snapshot);
        setSlow(m.slow_queries);
        setChanges(ch.changes);
        setHealth(h);
      } catch { /* server restarting */ }
    };
    load();
    const t = setInterval(load, 8000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const onPending = changes.filter((c) => c.status === "staged");
  const applied = changes.find((c) => c.status === "applied" && c.impact?.after_ms != null);
  const p99 = snapshot?.search_p99_ms ?? 0;
  const unhealthy = p99 >= 400;

  return (
    <>
      <div className="hero">
        <div className="panel" style={{ flex: 1, display: "flex", gap: 16, padding: "6px 4px" }}>
          <div className="hero-num" style={{ flex: 1 }}>
            <div className="k"><span className={`dot pulse`} style={{ color: unhealthy ? "var(--danger)" : "var(--ok)" }}>●</span> 门店搜索 P99（数据库实测）</div>
            <div className="v num" style={{ color: unhealthy ? "var(--danger)" : "var(--ok)" }}>
              {p99 || "—"}<small> ms</small>
            </div>
            <div style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 6 }}>
              {unhealthy ? "状态：异常 — 业务波动来自数据库，点击「数据库诊疗」排查" : "状态：健康 — 两个代理共享同一家店的数据"}
            </div>
          </div>
          <div className="link-arrow">⇄</div>
          <div className="hero-num" style={{ flex: 1 }}>
            <div className="k"><span style={{ color: "var(--violet)" }}>●</span> 下单转化率（模拟推算）</div>
            <div className="v num" style={{ color: "var(--violet)" }}>
              {snapshot ? snapshot.conversion_rate.toFixed(2) : "—"}<small> %</small>
            </div>
            <div style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 6 }}>
              延迟每拖 100ms，转化率按演示模型回落 0.45pct
            </div>
          </div>
          <div className="link-arrow">⇄</div>
          <div className="hero-num" style={{ flex: 1 }}>
            <div className="k"><span style={{ color: "var(--cyan)" }}>●</span> 今日订单 / 销售额</div>
            <div className="v num">{snapshot ? snapshot.orders_today.toLocaleString() : "—"}<small> 笔</small></div>
            <div style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 6 }} className="num">
              ¥{(snapshot?.revenue_today ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </div>
        </div>
      </div>

      <div className="split-2">
        <div className="panel">
          <div className="panel-head">
            <h3>业务 × 数据库 联动监测</h3>
            <span className="hint">近 12 小时 · search_log 实测数据，每 8 秒刷新</span>
          </div>
          <div className="panel-body">
            <DualChart series={snapshot?.series || []} />
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div className="panel">
            <div className="panel-head">
              <h3>架构联动</h3>
              <span className="hint">{health?.model} · MySQL {health?.mysql_version}</span>
            </div>
            <div className="panel-body">
              <div className="map">
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div className="map-node">
                    <div className="t">🛍 门店代理</div>
                    <div className="s">导购 · 订单查询 · 经营解读<br />真库搜索，延迟实时可见</div>
                  </div>
                  <div className="map-node">
                    <div className="t">👤 顾客 / 店主</div>
                    <div className="s">店面 · 运营台</div>
                  </div>
                </div>
                <div className="map-links">
                  <div className="map-link"><span className="wire flow" />工具调用</div>
                  <div className="map-link"><span className="wire" />SSE 事件</div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div className="map-node" style={{ borderColor: "rgba(45,212,255,0.35)" }}>
                    <div className="t">🩺 数据库诊疗代理</div>
                    <div className="s">慢查询 · EXPLAIN · 索引建议<br />写操作一律暂存待批</div>
                  </div>
                  <div className="map-node">
                    <div className="t">🗄 ops_demo</div>
                    <div className="s">goods 50 万 · orders 20 万<br />performance_schema 自报慢查询</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h3>数据库自报慢查询 TOP 3</h3>
              <span className="hint">performance_schema</span>
            </div>
            <div className="panel-body">
              <SlowQueryList items={slow} compact />
            </div>
          </div>
        </div>
      </div>

      {onPending.length > 0 ? (
        <div className="panel" style={{ borderColor: "rgba(167,139,250,0.4)" }}>
          <div className="panel-head">
            <h3>待审批变更（{onPending.length}）</h3>
            <span className="hint">批准按钮在这里才有效——聊天里说"同意"不算</span>
          </div>
          <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {onPending.map((c) => <ChangeCard key={c.change_id} change={c} />)}
          </div>
        </div>
      ) : null}

      {applied ? (
        <div className="panel">
          <div className="panel-head">
            <h3>已生效的优化</h3>
            <span className="hint">同一把尺子量出来的前后对比</span>
          </div>
          <div className="panel-body"><ChangeCard change={applied} /></div>
        </div>
      ) : null}

      <div className="entries">
        <button className="entry" onClick={() => go("store")}>
          <div className="t">🛍 顾客店面 <span className="pill info">业务侧</span></div>
          <div className="d">导购助手对接真实商品库。搜索框每次敲下，都能看到这条查询在数据库里的真实耗时。</div>
          <div className="who"><span className="pill muted">购物代理 · 读</span></div>
        </button>
        <button className="entry" onClick={() => go("ops")}>
          <div className="t">📊 店主运营台 <span className="pill violet">业务×技术</span></div>
          <div className="d">经营快照 + 延迟-转化联动解读。生意波动时，运营代理会指向数据库代理。</div>
          <div className="who"><span className="pill muted">门店代理 · 读</span></div>
        </button>
        <button className="entry" onClick={() => go("db")}>
          <div className="t">🩺 数据库诊疗台 <span className="pill danger">技术侧</span></div>
          <div className="d">慢查询、执行计划、实测耗时、索引建议。所有变更暂存待批，批准前零改动。</div>
          <div className="who"><span className="pill muted">数据库代理 · 读 + 暂存</span></div>
        </button>
      </div>
    </>
  );
}
