export type AgentEvent = {
  type: string;
  text?: string;
  tool?: string;
  label?: string;
  status?: string;
  summary?: string;
  component?: string;
  payload?: any;
  change?: StagedChange;
  message?: string;
  elapsed_ms?: number;
  rounds?: number;
  usage?: { input_tokens: number; output_tokens: number; cache_read: number };
};

export type DiffItem = { target: string; field: string; before: any; after: any };

export type StagedChange = {
  change_id: string;
  kind: string;
  status: "staged" | "applied" | "discarded";
  summary: string;
  sql: string;
  items: DiffItem[];
  impact: Record<string, any>;
  created_at: string;
  created_by: string;
  created_by_kind: string;
  applied_at?: string | null;
  applied_by?: string | null;
  discarded_at?: string | null;
  discarded_by?: string | null;
};

export type SlowQuery = {
  digest: string;
  count_star: number;
  total_sec: number;
  avg_ms: number;
  rows_examined: number;
  sample_text: string;
};

export type Product = {
  id: number; name: string; category: string;
  price: number; stock: number; sales_30d: number;
};

export type Bucket = { bucket: string; avg_ms: number; max_ms: number; conversion: number };

export type Snapshot = {
  orders_today: number;
  revenue_today: number;
  search_p99_ms: number;
  search_avg_ms: number;
  conversion_rate: number;
  db_healthy: boolean;
  series: Bucket[];
};

const BASE = "";

export async function startSession(agent: string): Promise<string> {
  const r = await fetch(`${BASE}/api/${agent}/session`, { method: "POST" });
  return (await r.json()).session_id as string;
}

/** Stream one chat turn as UI events. */
export async function streamChat(
  agent: string,
  sessionId: string,
  message: string,
  onEvent: (e: AgentEvent) => void,
): Promise<void> {
  const resp = await fetch(`${BASE}/api/${agent}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Session-Id": sessionId },
    body: JSON.stringify({ message }),
  });
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) {
          try { onEvent(JSON.parse(line.slice(6))); } catch { /* keep-alive or partial */ }
        }
      }
    }
  }
}

export async function getJSON<T = any>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

export async function postJSON<T = any>(path: string, body: any): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const detail = await r.text();
    throw new Error(detail.slice(0, 200));
  }
  return r.json();
}

/** Chat turn status lines, in Chinese, keyed by tool name. */
export const TOOL_COPY: Record<string, string> = {
  load_skill: "加载流程手册",
  get_slow_queries: "读取数据库自报的慢查询",
  get_table_info: "查看表结构与索引",
  explain_query: "解析执行计划",
  measure_query: "实测查询耗时",
  stage_index_change: "暂存索引变更（待审批）",
  get_pending_changes: "查看待审批变更",
  search_products: "搜索门店数据库",
  get_product: "读取商品详情",
  get_my_orders: "查询顾客订单",
  get_business_snapshot: "读取经营快照",
};
