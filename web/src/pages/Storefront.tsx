import { useState } from "react";
import { getJSON } from "../api";
import { ProductGrid } from "../cards";
import { Chat } from "../chat";

export function Storefront() {
  const [keyword, setKeyword] = useState("帐篷");
  const [items, setItems] = useState<any[]>([]);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [searching, setSearching] = useState(false);

  const search = async (kw?: string) => {
    const q = kw ?? keyword;
    if (!q.trim()) return;
    setKeyword(q);
    setSearching(true);
    try {
      const data = await getJSON(`/api/commerce/search?keyword=${encodeURIComponent(q)}`);
      setItems(data.items);
      setElapsed(data.elapsed_ms);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="split-2">
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="panel">
          <div className="panel-head">
            <h3>ACME 演示商城</h3>
            <span className="hint">商品数据在 ops_demo.goods（50 万行，真实查询）</span>
          </div>
          <div className="panel-body">
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && search()}
                placeholder="搜点什么：帐篷 / 耳机 / 瑜伽…"
                style={{
                  flex: 1, background: "var(--panel-strong)", border: "1px solid var(--line)",
                  borderRadius: 12, color: "var(--ink)", padding: "10px 14px", fontSize: 14, outline: "none",
                }}
              />
              <button className="btn primary" disabled={searching} onClick={() => search()}>
                {searching ? "搜索中…" : "搜索"}
              </button>
              {elapsed != null ? (
                <span className={`lat-badge ${elapsed > 300 ? "slow" : elapsed > 80 ? "" : "fast"}`}>
                  {elapsed} ms · 数据库实测
                </span>
              ) : null}
            </div>
            <div style={{ marginTop: 14 }}>
              {items.length ? (
                <ProductGrid items={items} />
              ) : (
                <p style={{ color: "var(--ink-soft)", fontSize: 13 }}>
                  输入关键词搜索，或在右侧让导购助手帮你找。每条搜索都会计入左下的延迟日志——这就是数据库代理看到的原始证据。
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h3>我的订单</h3>
            <span className="hint">演示账号 user_id=42 · 这条查询在 orders 表（20 万行）上没有索引可用</span>
          </div>
          <div className="panel-body">
            <OrdersLoader />
          </div>
        </div>
      </div>

      <div className="chat-panel panel">
        <div className="panel-head"><h3>导购助手</h3><span className="hint">购物代理 · 只有读权限</span></div>
        <Chat
          agent="commerce"
          height={520}
          starters={[
            "帮我找一顶适合两个人露营的帐篷",
            "700 元以内有什么数码配件值得买？",
            "查一下用户 42 的最近订单",
            "为什么现在搜索有点卡？",
          ]}
        />
      </div>
    </div>
  );
}

function OrdersLoader() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      setData(await getJSON("/api/commerce/orders?user_id=42"));
    } finally {
      setLoading(false);
    }
  };
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
        <button className="btn sm" disabled={loading} onClick={load}>{loading ? "查询中…" : "查询我的订单"}</button>
        {data ? (
          <span className={`lat-badge ${data.elapsed_ms > 300 ? "slow" : "slow"}`}>
            {data.elapsed_ms} ms · 无索引全表扫描
          </span>
        ) : null}
      </div>
      {data ? (
        <table className="tbl">
          <thead><tr><th>订单</th><th>金额</th><th>状态</th><th>时间</th></tr></thead>
          <tbody>
            {data.items.map((o: any) => (
              <tr key={o.id}>
                <td className="num">#{o.id}</td>
                <td className="num">¥{o.total}</td>
                <td style={{ color: "var(--ink-soft)" }}>{o.status}</td>
                <td className="num" style={{ color: "var(--ink-soft)" }}>{o.created_at?.slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p style={{ color: "var(--ink-soft)", fontSize: 12.5, margin: 0 }}>
          点「查询我的订单」——这条查询会真实扫过 20 万行订单表，耗时记录会同时出现在数据库代理的慢查询榜上。
        </p>
      )}
    </>
  );
}
