import { useEffect, useState } from "react";
import { Dashboard } from "./pages/Dashboard";
import { Storefront } from "./pages/Storefront";
import { Ops } from "./pages/Ops";
import { Database } from "./pages/Database";

const NAV: { id: string; ico: string; label: string }[] = [
  { id: "dashboard", ico: "◉", label: "联动大屏" },
  { id: "store", ico: "🛍", label: "顾客店面" },
  { id: "ops", ico: "📊", label: "店主运营台" },
  { id: "db", ico: "🩺", label: "数据库诊疗台" },
];

const TITLES: Record<string, { h1: string; sub: string }> = {
  dashboard: { h1: "业务 × 数据库 联动大屏", sub: "两个代理，一家店，一个真实的 MySQL——业务波动和技术故障在这里互为因果" },
  store: { h1: "顾客店面", sub: "购物代理对接真实商品库；每一次搜索的数据库耗时都当场可见" },
  ops: { h1: "店主运营台", sub: "经营解读 + 延迟归因：业务侧的异常，会指向技术侧的根因" },
  db: { h1: "数据库诊疗台", sub: "诊断有门控，写入有审批——代理的每一步都看得见、拦得住" },
};

export default function App() {
  const [page, setPage] = useState(() => (location.hash || "#dashboard").slice(1));
  useEffect(() => {
    const onHash = () => setPage((location.hash || "#dashboard").slice(1));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const go = (p: string) => {
    location.hash = p;
    setPage(p);
  };
  const title = TITLES[page] || TITLES.dashboard;

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">
          <div className="brand-mark">O</div>
          <div>
            <div className="brand-name">OpsAgents</div>
            <div className="brand-sub">业务×数据库 双代理工作台</div>
          </div>
        </div>
        <nav>
          {NAV.map((n) => (
            <button key={n.id} className={`nav-item ${page === n.id ? "on" : ""}`} onClick={() => go(n.id)}>
              <span className="ico">{n.ico}</span>
              <span className="txt">{n.label}</span>
            </button>
          ))}
        </nav>
        <div className="rail-foot">
          治理层演示<br />
          读有门控 · 写有审批<br />
          <span style={{ color: "var(--ink-faint)" }}>数据全部来自本机 MySQL ops_demo</span>
        </div>
      </aside>
      <main className="main">
        <div className="main-inner">
          <div className="page-head">
            <h1>{title.h1}</h1>
            <p>{title.sub}</p>
          </div>
          {page === "store" ? <Storefront /> : page === "ops" ? <Ops go={go} /> : page === "db" ? <Database /> : <Dashboard go={go} />}
        </div>
      </main>
    </div>
  );
}
