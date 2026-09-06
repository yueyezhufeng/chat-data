import { useEffect, useState } from "react";
import { getJSON, type SlowQuery, type StagedChange } from "../api";
import { ChangeCard, SlowQueryList } from "../cards";
import { Chat } from "../chat";

export function Database() {
  const [slow, setSlow] = useState<SlowQuery[]>([]);
  const [tables, setTables] = useState<any[]>([]);
  const [changes, setChanges] = useState<StagedChange[]>([]);
  const [version, setVersion] = useState("");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [m, ch] = await Promise.all([getJSON("/api/mysql/overview"), getJSON("/api/changes")]);
        if (!alive) return;
        setSlow(m.slow_queries);
        setTables(m.tables);
        setVersion(m.version);
        setChanges(ch.changes);
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 6000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const pending = changes.filter((c) => c.status === "staged");

  return (
    <div className="split-2">
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="panel">
          <div className="panel-head">
            <h3>数据库自报慢查询榜</h3>
            <span className="hint">performance_schema · MySQL {version} · ops_demo</span>
          </div>
          <div className="panel-body"><SlowQueryList items={slow} /></div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h3>表概况</h3>
            <span className="hint">故意保留的"未调优"状态是演示的一部分</span>
          </div>
          <div className="panel-body">
            <table className="tbl">
              <thead><tr><th>表</th><th>行数</th><th>大小</th><th>二级索引</th></tr></thead>
              <tbody>
                {tables.map((t) => (
                  <tr key={t.table}>
                    <td className="num">{t.table}</td>
                    <td className="num">{t.rows.toLocaleString()}</td>
                    <td className="num">{t.size_mb} MB</td>
                    <td>
                      {Object.keys(t.indexes).filter((k) => k !== "PRIMARY").length ? (
                        <span className="num" style={{ color: "var(--ink-2)" }}>
                          {Object.entries(t.indexes).filter(([k]) => k !== "PRIMARY").map(([k, v]) => `${k}(${(v as string[]).join(",")})`).join("；")}
                        </span>
                      ) : (
                        <span className="pill danger">除主键外无索引</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {pending.length ? (
          <div className="panel" style={{ borderColor: "rgba(167,139,250,0.45)" }}>
            <div className="panel-head">
              <h3>待审批（{pending.length}）</h3>
              <span className="hint">这里是唯一的批准入口</span>
            </div>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {pending.map((c) => (
                <ChangeCard key={c.change_id} change={c}
                  onUpdate={(nc) => setChanges((prev) => prev.map((x) => (x.change_id === nc.change_id ? nc : x)))} />
              ))}
            </div>
          </div>
        ) : null}

        {changes.filter((c) => c.status !== "staged").length ? (
          <div className="panel">
            <div className="panel-head"><h3>变更历史</h3><span className="hint"> newest first</span></div>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {changes.filter((c) => c.status !== "staged").map((c) => (
                <ChangeCard key={c.change_id} change={c}
                  onUpdate={(nc) => setChanges((prev) => prev.map((x) => (x.change_id === nc.change_id ? nc : x)))} />
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div className="chat-panel panel">
        <div className="panel-head"><h3>数据库诊疗代理</h3><span className="hint">读 + 暂存 · 无执行权限</span></div>
        <Chat
          agent="mysql"
          height={620}
          onChangeUpdate={(nc) => setChanges((prev) => {
            const exists = prev.some((x) => x.change_id === nc.change_id);
            return exists ? prev.map((x) => (x.change_id === nc.change_id ? nc : x)) : [nc, ...prev];
          })}
          starters={[
            "店里反馈系统很卡，帮我排查一下",
            "看看 orders 表的执行计划，为什么查询慢",
            "给慢查询出一个索引优化方案",
            "直接 DELETE FROM orders 可以吗？",
          ]}
        />
      </div>
    </div>
  );
}
