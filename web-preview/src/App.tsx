import { useState, useEffect, useRef, useCallback, FC, CSSProperties, KeyboardEvent } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

type TaskStatus = "queued" | "leased" | "in_progress" | "completed" | "failed" | "retrying";
type AgentType  = "prompt-based" | "langgraph";
type TaskType   = "research" | "analyze_documents" | "summarize" | "custom";
type FilterType = "all" | TaskStatus;

interface TaskParams {
  query?: string;
  [key: string]: unknown;
}

interface TaskResult {
  status?: string;
  message?: string;
  [key: string]: unknown;
}

interface Task {
  task_id: string;
  status: TaskStatus;
  tenant_id: string;
  agent_type: AgentType;
  task_type: string;
  task_params: TaskParams;
  cost_so_far: number;
  cost_limit?: number;
  attempts: number;
  max_attempts: number;
  owner?: string | null;
  current_node?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  result?: TaskResult | null;
  error?: string | null;
}

interface TaskListResponse {
  tasks: Task[];
  total: number;
}

interface Stats {
  total_tasks: number;
  queued: number;
  leased: number;
  in_progress: number;
  completed: number;
  failed: number;
  retrying: number;
}

interface HealthResponse {
  status: string;
  redis_connected: boolean;
  timestamp: string;
}

interface CreateTaskPayload {
  task_type: string;
  tenant_id: string;
  agent_type: AgentType;
  task_params: TaskParams;
  cost_limit: number;
  max_attempts: number;
}

interface SubmitFormState {
  task_type: TaskType;
  tenant_id: string;
  agent_type: AgentType;
  query: string;
  cost_limit: number;
  max_attempts: number;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const API_BASE = "https://unlured-tearingly-alondra.ngrok-free.dev";
const GITHUB_REPO = "https://github.com/ray-singh/Sentinel-Node-Orchestrator";
const POLL_INTERVAL_MS = 3000;
const NODE_SEQUENCE = ["start", "search", "analyze", "summarize", "complete"] as const;
type NodeName = typeof NODE_SEQUENCE[number];

interface StatusMeta {
  color: string;
  text: string;
  dot: string;
  label: string;
}

const STATUS_META: Record<TaskStatus, StatusMeta> = {
  queued:      { color: "#B5D4F4", text: "#0C447C", dot: "#378ADD", label: "Queued"   },
  leased:      { color: "#FAC775", text: "#633806", dot: "#BA7517", label: "Leased"   },
  in_progress: { color: "#C0DD97", text: "#27500A", dot: "#639922", label: "Running"  },
  completed:   { color: "#9FE1CB", text: "#085041", dot: "#1D9E75", label: "Done"     },
  failed:      { color: "#F7C1C1", text: "#791F1F", dot: "#E24B4A", label: "Failed"   },
  retrying:    { color: "#EEEDFE", text: "#3C3489", dot: "#7F77DD", label: "Retrying" },
};

const ACTIVE_STATUSES = new Set<TaskStatus>(["queued", "leased", "in_progress"]);
const TERMINAL_STATUSES = new Set<TaskStatus>(["completed", "failed"]);

// ─── API hook ─────────────────────────────────────────────────────────────────

function useApi() {
  const call = useCallback(async (path: string, opts: RequestInit = {}) => {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (res.status === 204) return null;
    return res.json();
  }, []);

  return function<T = any>(path: string, opts: RequestInit = {}): Promise<T | null> {
    return call(path, opts) as Promise<T | null>;
  };
}

// ─── StatusBadge ─────────────────────────────────────────────────────────────

interface StatusBadgeProps { status: TaskStatus; }

const StatusBadge: FC<StatusBadgeProps> = ({ status }) => {
  const m = STATUS_META[status] ?? STATUS_META.queued;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      background: m.color, color: m.text,
      fontSize: 11, fontWeight: 500, padding: "3px 8px",
      borderRadius: 99, letterSpacing: "0.02em", flexShrink: 0,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: m.dot }} />
      {m.label}
    </span>
  );
};

// ─── NodeTimeline ─────────────────────────────────────────────────────────────

interface NodeTimelineProps { task: Task; }

const NodeTimeline: FC<NodeTimelineProps> = ({ task }) => {
  const current = (task.current_node ?? "start") as NodeName;
  const currentIdx = NODE_SEQUENCE.indexOf(current);

  return (
    <div style={{ display: "flex", alignItems: "center" }}>
      {NODE_SEQUENCE.map((node, i) => {
        const done    = i < currentIdx || task.status === "completed";
        const active  = i === currentIdx && !TERMINAL_STATUSES.has(task.status);
        const failed  = task.status === "failed" && i === currentIdx;
        const notYet  = !done && !active && !failed;

        const dotBg     = failed ? "#E24B4A" : done ? "#1D9E75" : active ? "#378ADD" : "var(--color-background-secondary)";
        const dotBorder = failed ? "#E24B4A" : done ? "#1D9E75" : active ? "#378ADD" : "var(--color-border-tertiary)";
        const lineBg    = done ? "#1D9E75" : "var(--color-border-tertiary)";

        return (
          <div key={node} style={{ display: "flex", alignItems: "center", flex: i < NODE_SEQUENCE.length - 1 ? 1 : "initial" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
              <div style={{
                width: 20, height: 20, borderRadius: "50%",
                background: dotBg,
                border: `1.5px solid ${dotBorder}`,
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.3s",
              }}>
                {done   && <Checkmark />}
                {active && <div style={{ width: 6, height: 6, borderRadius: "50%", background: "white", animation: "pulse 1s infinite" }} />}
                {failed && <span style={{ color: "white", fontSize: 10, fontWeight: 700, lineHeight: 1 }}>✕</span>}
              </div>
              <span style={{
                fontSize: 9,
                color: active ? "var(--color-text-primary)" : "var(--color-text-tertiary)",
                whiteSpace: "nowrap",
                fontWeight: active ? 500 : 400,
              }}>
                {node}
              </span>
            </div>
            {i < NODE_SEQUENCE.length - 1 && (
              <div style={{ flex: 1, height: 1.5, background: lineBg, marginBottom: 14, transition: "background 0.3s" }} />
            )}
          </div>
        );
      })}
    </div>
  );
};

const Checkmark: FC = () => (
  <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
    <path d="M1 3.5L3.5 6L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

// ─── TaskCard ─────────────────────────────────────────────────────────────────

interface TaskCardProps {
  task: Task;
  onCancel: (id: string) => void;
  selected: boolean;
  onClick: () => void;
}

const TaskCard: FC<TaskCardProps> = ({ task, onCancel, selected, onClick }) => (
  <div
    onClick={onClick}
    style={{
      background: "var(--color-background-primary)",
      border: `0.5px solid ${selected ? "var(--color-border-primary)" : "var(--color-border-tertiary)"}`,
      borderLeft: selected ? "3px solid #378ADD" : "0.5px solid var(--color-border-tertiary)",
      borderRadius: "var(--border-radius-lg)",
      padding: "12px 14px",
      cursor: "pointer",
      transition: "border-color 0.15s",
    }}
  >
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
      <div style={{ minWidth: 0, marginRight: 8 }}>
        <p style={{ margin: 0, fontSize: 13, fontWeight: 500, color: "var(--color-text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {task.task_type}
        </p>
        <p style={{ margin: "2px 0 0", fontSize: 11, color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {task.task_id.slice(0, 22)}
        </p>
      </div>
      <StatusBadge status={task.status} />
    </div>

    {task.task_params.query && (
      <p style={{
        margin: "6px 0 0", fontSize: 12,
        color: "var(--color-text-secondary)", lineHeight: 1.5,
        overflow: "hidden", display: "-webkit-box",
        WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
      }}>
        {task.task_params.query}
      </p>
    )}

    <div style={{ marginTop: 8 }}>
      <NodeTimeline task={task} />
    </div>

    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      marginTop: 10, paddingTop: 8,
      borderTop: "0.5px solid var(--color-border-tertiary)",
    }}>
      <div style={{ display: "flex", gap: 10 }}>
        <MetaChip>${task.cost_so_far.toFixed(4)}</MetaChip>
        <MetaChip>attempt {task.attempts}/{task.max_attempts}</MetaChip>
        <MetaChip>{task.agent_type}</MetaChip>
      </div>
      {ACTIVE_STATUSES.has(task.status) && (
        <button
          onClick={e => { e.stopPropagation(); onCancel(task.task_id); }}
          style={{
            fontSize: 11, color: "var(--color-text-danger)",
            background: "none", border: "none", cursor: "pointer",
            padding: "2px 6px", borderRadius: "var(--border-radius-md)",
          }}
        >
          Cancel
        </button>
      )}
    </div>
  </div>
);

const MetaChip: FC<{ children: React.ReactNode }> = ({ children }) => (
  <span style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{children}</span>
);

// ─── SubmitForm ───────────────────────────────────────────────────────────────

interface SubmitFormProps {
  onSubmit: (payload: CreateTaskPayload) => void;
  loading: boolean;
}

const SubmitForm: FC<SubmitFormProps> = ({ onSubmit, loading }) => {
  const [form, setForm] = useState<SubmitFormState>({
    task_type:    "research",
    tenant_id:    "tenant-1",
    agent_type:   "prompt-based",
    query:        "",
    cost_limit:   2.0,
    max_attempts: 3,
  });

  const set = <K extends keyof SubmitFormState>(key: K, value: SubmitFormState[K]) =>
    setForm(prev => ({ ...prev, [key]: value }));

  const canSubmit = !loading && form.query.trim().length > 0;

  const handleSubmit = () => {
    if (!canSubmit) return;
    onSubmit({
      task_type:   form.task_type,
      tenant_id:   form.tenant_id,
      agent_type:  form.agent_type,
      task_params: { query: form.query.trim() },
      cost_limit:  Number(form.cost_limit),
      max_attempts: Number(form.max_attempts),
    });
    set("query", "");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && e.metaKey) handleSubmit();
  };

  const labelStyle: CSSProperties = { fontSize: 11, color: "var(--color-text-secondary)", display: "block", marginBottom: 4 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <textarea
        value={form.query}
        onChange={e => set("query", e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="What should the agent do? e.g. Research the latest advances in vector databases…"
        rows={3}
        style={{ resize: "vertical", fontSize: 13, fontFamily: "var(--font-sans)" }}
      />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <div>
          <label style={labelStyle}>Task type</label>
          <select value={form.task_type} onChange={e => set("task_type", e.target.value as TaskType)} style={{ width: "100%", fontSize: 12 }}>
            <option value="research">Research</option>
            <option value="analyze_documents">Analyze documents</option>
            <option value="summarize">Summarize</option>
            <option value="custom">Custom</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>Agent</label>
          <select value={form.agent_type} onChange={e => set("agent_type", e.target.value as AgentType)} style={{ width: "100%", fontSize: 12 }}>
            <option value="prompt-based">Prompt-based</option>
            <option value="langgraph">LangGraph</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>Tenant</label>
          <input
            value={form.tenant_id}
            onChange={e => set("tenant_id", e.target.value)}
            style={{ width: "100%", fontSize: 12, boxSizing: "border-box" }}
          />
        </div>
        <div>
          <label style={labelStyle}>Cost limit ($)</label>
          <input
            type="number" step="0.5" min="0.1"
            value={form.cost_limit}
            onChange={e => set("cost_limit", parseFloat(e.target.value))}
            style={{ width: "100%", fontSize: 12, boxSizing: "border-box" }}
          />
        </div>
      </div>

      <button
        onClick={handleSubmit}
        disabled={!canSubmit}
        style={{ alignSelf: "flex-end", padding: "7px 18px", fontSize: 13, fontWeight: 500, opacity: canSubmit ? 1 : 0.5 }}
      >
        {loading ? "Submitting…" : "Submit task ↗"}
      </button>
    </div>
  );
};

// ─── StatCard ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: number | string;
  color?: string;
}

const StatCard: FC<StatCardProps> = ({ label, value, color }) => (
  <div style={{ background: "var(--color-background-secondary)", borderRadius: "var(--border-radius-md)", padding: "10px 14px" }}>
    <p style={{ margin: 0, fontSize: 11, color: "var(--color-text-secondary)" }}>{label}</p>
    <p style={{ margin: "3px 0 0", fontSize: 22, fontWeight: 500, color: color ?? "var(--color-text-primary)" }}>{value}</p>
  </div>
);

// ─── SectionLabel ─────────────────────────────────────────────────────────────

const SectionLabel: FC<{ children: React.ReactNode }> = ({ children }) => (
  <p style={{
    margin: "0 0 10px", fontSize: 12, fontWeight: 500,
    color: "var(--color-text-secondary)",
    textTransform: "uppercase", letterSpacing: "0.06em",
  }}>
    {children}
  </p>
);

// ─── DetailRow ────────────────────────────────────────────────────────────────

interface DetailRowProps { label: string; value: string; mono?: boolean; }

const DetailRow: FC<DetailRowProps> = ({ label, value, mono }) => (
  <tr>
    <td style={{ padding: "5px 0", color: "var(--color-text-secondary)", width: "45%", fontSize: 12 }}>{label}</td>
    <td style={{
      padding: "5px 0", color: "var(--color-text-primary)",
      fontSize: mono ? 11 : 12,
      fontFamily: mono ? "var(--font-mono)" : "inherit",
    }}>
      {value}
    </td>
  </tr>
);

// ─── DetailPanel ──────────────────────────────────────────────────────────────

interface DetailPanelProps { task: Task | null; }

const DetailPanel: FC<DetailPanelProps> = ({ task }) => {
  if (!task) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--color-text-tertiary)", fontSize: 13 }}>
        Select a task to inspect
      </div>
    );
  }

  const divider: CSSProperties = { borderTop: "0.5px solid var(--color-border-tertiary)", paddingTop: 14, marginBottom: 14 };

  return (
    <div style={{ overflowY: "auto", height: "100%" }}>
      {/* Identity */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <StatusBadge status={task.status} />
          <span style={{ fontSize: 11, color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>
            {task.task_id}
          </span>
        </div>
        <p style={{ margin: 0, fontSize: 15, fontWeight: 500 }}>{task.task_type}</p>
        {task.task_params.query && (
          <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
            {task.task_params.query}
          </p>
        )}
      </div>

      {/* Progress */}
      <div style={divider}>
        <SectionLabel>Progress</SectionLabel>
        <NodeTimeline task={task} />
      </div>

      {/* Metadata */}
      <div style={divider}>
        <SectionLabel>Metadata</SectionLabel>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <tbody>
            <DetailRow label="Tenant"     value={task.tenant_id} mono />
            <DetailRow label="Agent"      value={task.agent_type} />
            <DetailRow label="Cost so far" value={`$${task.cost_so_far.toFixed(6)}`} />
            <DetailRow label="Cost limit"  value={`$${(task.cost_limit ?? 0).toFixed(2)}`} />
            <DetailRow label="Attempts"   value={`${task.attempts} / ${task.max_attempts}`} />
            <DetailRow label="Owner"      value={task.owner ?? "—"} mono />
            <DetailRow label="Created"    value={new Date(task.created_at).toLocaleString()} />
            <DetailRow label="Updated"    value={new Date(task.updated_at).toLocaleString()} />
            {task.completed_at && (
              <DetailRow label="Completed" value={new Date(task.completed_at).toLocaleString()} />
            )}
          </tbody>
        </table>
      </div>

      {/* Error */}
      {task.error && (
        <div style={{ borderTop: "0.5px solid var(--color-border-danger)", paddingTop: 14, marginBottom: 14 }}>
          <SectionLabel>Error</SectionLabel>
          <p style={{
            margin: 0, fontSize: 12, color: "var(--color-text-danger)", lineHeight: 1.5,
            fontFamily: "var(--font-mono)", background: "var(--color-background-danger)",
            padding: "8px 10px", borderRadius: "var(--border-radius-md)",
          }}>
            {task.error}
          </p>
        </div>
      )}

      {/* Result */}
      {task.result && (
        <div style={divider}>
          <SectionLabel>Result</SectionLabel>
          <pre style={{
            margin: 0, fontSize: 11, fontFamily: "var(--font-mono)",
            background: "var(--color-background-secondary)",
            padding: "10px 12px", borderRadius: "var(--border-radius-md)",
            overflow: "auto", lineHeight: 1.5,
            whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>
            {JSON.stringify(task.result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};

const ApiUnreachableModal: FC<{ onRetry: () => void }> = ({ onRetry }) => (
  <div style={{ position: "fixed", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(2,6,23,0.45)", zIndex: 9999 }}>
    <div style={{ width: 480, background: "var(--color-background-primary)", borderRadius: "var(--border-radius-lg)", padding: 18, boxShadow: "var(--shadow-md)" }}>
      <h3 style={{ margin: 0, fontSize: 16 }}>API Unreachable</h3>
      <p style={{ marginTop: 8, color: "var(--color-text-secondary)" }}>
        I turned the backend off to keep deployment costs down, so the dashboard can't reach it right now. I apologize for any inconvenience. 
        You can view the source code and instructions in the GitHub repository below if you'd like to run it locally or deploy your own instance.
      </p>
      <p style={{ marginTop: 6 }}>
        <a href={GITHUB_REPO} target="_blank" rel="noopener noreferrer" style={{ color: "#0b61d6" }}>Open repository on GitHub</a>
      </p>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
        <button className="btn-ghost" onClick={onRetry} style={{ padding: "7px 12px" }}>Retry</button>
        <button onClick={() => window.location.reload()} style={{ padding: "7px 12px" }}>Reload</button>
      </div>
    </div>
  </div>
);

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const api    = useApi();
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [tasks,      setTasks]      = useState<Task[]>([]);
  const [stats,      setStats]      = useState<Stats | null>(null);
  const [selected,   setSelected]   = useState<Task | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error,      setError]      = useState<string | null>(null);
  const [filter,     setFilter]     = useState<FilterType>("all");
  const [apiOk,      setApiOk]      = useState<boolean | null>(null);

  const selectedId = selected?.task_id ?? null;

  const fetchTasks = useCallback(async () => {
    try {
      const data = await api<TaskListResponse>("/tasks?limit=50");
      if (!data) return;
      const list = data.tasks ?? [];
      setTasks(list);
      if (selectedId) {
        const updated = list.find(t => t.task_id === selectedId);
        if (updated) setSelected(updated);
      }
    } catch {}
  }, [api, selectedId]);

  const fetchStats = useCallback(async () => {
    try {
      const data = await api<Stats>("/stats");
      if (data) setStats(data);
    } catch {}
  }, [api]);

  const checkHealth = useCallback(async () => {
    try {
      const data = await api<HealthResponse>("/health");
      setApiOk(data?.redis_connected ?? false);
    } catch {
      setApiOk(false);
    }
  }, [api]);

  useEffect(() => {
    checkHealth();
    fetchTasks();
    fetchStats();
    pollRef.current = setInterval(() => { fetchTasks(); fetchStats(); }, POLL_INTERVAL_MS);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = async (payload: CreateTaskPayload) => {
    setSubmitting(true);
    setError(null);
    try {
      const task = await api<Task>("/tasks", { method: "POST", body: JSON.stringify(payload) });
      if (task) {
        setTasks(prev => [task, ...prev]);
        setSelected(task);
        fetchStats();
      }
    } catch {
      setError("Failed to submit task. Is the API running at localhost:8000?");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async (taskId: string) => {
    try {
      await api(`/tasks/${taskId}`, { method: "DELETE" });
      fetchTasks();
      fetchStats();
    } catch {}
  };

  const filtered  = tasks.filter(t => filter === "all" || t.status === filter);
  const active    = tasks.filter(t => ACTIVE_STATUSES.has(t.status));
  const terminal  = tasks.filter(t => TERMINAL_STATUSES.has(t.status));
  const totalCost = tasks.reduce((s, t) => s + t.cost_so_far, 0);

  const headerStyle: CSSProperties = {
    background: "var(--color-background-primary)",
    borderBottom: "0.5px solid var(--color-border-tertiary)",
    padding: "10px 20px",
    display: "flex", alignItems: "center", justifyContent: "space-between",
    flexShrink: 0,
  };

  const panelHeaderStyle: CSSProperties = {
    padding: "12px 16px",
    borderBottom: "0.5px solid var(--color-border-tertiary)",
    flexShrink: 0,
    background: "var(--color-background-primary)",
  };

  return (
    <div style={{ fontFamily: "var(--font-sans)", height: "100vh", display: "flex", flexDirection: "column", background: "var(--color-background-tertiary)" }}>
      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}`}</style>

      {/* ── Header ── */}
      <div style={headerStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
            background: apiOk === null ? "#888" : apiOk ? "#1D9E75" : "#E24B4A",
          }} />
          <span style={{ fontSize: 14, fontWeight: 500 }}>Sentinel</span>
          <span style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
            {apiOk === null ? "connecting…" : apiOk ? "api connected" : "api unreachable"}
          </span>
        </div>
        <div style={{ display: "flex", gap: 16, fontSize: 12, color: "var(--color-text-secondary)" }}>
          <span><strong style={{ color: "var(--color-text-primary)" }}>{tasks.length}</strong> tasks</span>
          <span><strong style={{ color: active.length > 0 ? "#378ADD" : "var(--color-text-primary)" }}>{active.length}</strong> running</span>
          <span><strong style={{ color: "var(--color-text-primary)" }}>${totalCost.toFixed(4)}</strong> total cost</span>
        </div>
      </div>

      {/* ── Three-column body ── */}
      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "320px 1fr 300px", overflow: "hidden", minHeight: 0 }}>

        {/* ── Left: submit + task list ── */}
        <div style={{ borderRight: "0.5px solid var(--color-border-tertiary)", display: "flex", flexDirection: "column", overflow: "hidden" }}>

          {/* Submit */}
          <div style={{ padding: 16, borderBottom: "0.5px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", flexShrink: 0 }}>
            <SectionLabel>Submit task</SectionLabel>
            <SubmitForm onSubmit={handleSubmit} loading={submitting} />
            {error && <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--color-text-danger)" }}>{error}</p>}
          </div>

          {/* Filters */}
          <div style={{ padding: "8px 16px", borderBottom: "0.5px solid var(--color-border-tertiary)", flexShrink: 0, display: "flex", gap: 6, flexWrap: "wrap" }}>
            {(["all", "queued", "in_progress", "completed", "failed"] as FilterType[]).map(f => {
              const active = filter === f;
              return (
                <button key={f} onClick={() => setFilter(f)} style={{
                  fontSize: 11, padding: "3px 8px", borderRadius: 99, cursor: "pointer",
                  background: active ? "var(--color-background-info)"  : "var(--color-background-secondary)",
                  color:      active ? "var(--color-text-info)"        : "var(--color-text-secondary)",
                  border:     active ? "0.5px solid var(--color-border-info)" : "0.5px solid var(--color-border-tertiary)",
                }}>
                  {f === "all" ? `All (${tasks.length})` : f.replace("_", " ")}
                </button>
              );
            })}
          </div>

          {/* Task list */}
          <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            {filtered.length === 0 && (
              <p style={{ fontSize: 13, color: "var(--color-text-tertiary)", textAlign: "center", marginTop: 40 }}>
                {tasks.length === 0 ? "No tasks yet. Submit one above." : "No tasks match this filter."}
              </p>
            )}
            {filtered.map(task => (
              <TaskCard
                key={task.task_id}
                task={task}
                onCancel={handleCancel}
                selected={selected?.task_id === task.task_id}
                onClick={() => setSelected(task)}
              />
            ))}
          </div>
        </div>

        {/* ── Center: live activity ── */}
        <div style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={panelHeaderStyle}>
            <p style={{ margin: 0, fontSize: 12, fontWeight: 500, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Live activity
            </p>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>

            {/* Stat cards */}
            {stats && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 10, marginBottom: 20 }}>
                <StatCard label="Total"   value={stats.total_tasks} />
                <StatCard label="Queued"  value={stats.queued}      color="#378ADD" />
                <StatCard label="Running" value={(stats.leased ?? 0) + (stats.in_progress ?? 0)} color="#BA7517" />
                <StatCard label="Done"    value={stats.completed}   color="#1D9E75" />
              </div>
            )}

            {/* Active pipelines */}
            <div style={{ marginBottom: 20 }}>
              <SectionLabel>Active pipelines</SectionLabel>
              {active.length === 0 ? (
                <EmptyState>No active tasks</EmptyState>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {active.map(task => (
                    <div
                      key={task.task_id}
                      onClick={() => setSelected(task)}
                      style={{
                        background: "var(--color-background-primary)",
                        border: "0.5px solid var(--color-border-tertiary)",
                        borderRadius: "var(--border-radius-lg)",
                        padding: "12px 16px", cursor: "pointer",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <StatusBadge status={task.status} />
                          <span style={{ fontSize: 12, fontWeight: 500 }}>{task.task_type}</span>
                        </div>
                        <span style={{ fontSize: 11, color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>
                          {task.tenant_id}
                        </span>
                      </div>
                      <NodeTimeline task={task} />
                      {task.task_params.query && (
                        <p style={{ margin: "8px 0 0", fontSize: 11, color: "var(--color-text-secondary)", overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>
                          {task.task_params.query}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Recent completions */}
            <div>
              <SectionLabel>Recent completions</SectionLabel>
              {terminal.length === 0 ? (
                <p style={{ fontSize: 13, color: "var(--color-text-tertiary)", margin: 0 }}>No completed tasks yet.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {terminal.slice(0, 8).map(task => (
                    <div
                      key={task.task_id}
                      onClick={() => setSelected(task)}
                      style={{
                        background: "var(--color-background-primary)",
                        border: "0.5px solid var(--color-border-tertiary)",
                        borderRadius: "var(--border-radius-md)",
                        padding: "8px 12px",
                        display: "flex", alignItems: "center", gap: 10, cursor: "pointer",
                      }}
                    >
                      <StatusBadge status={task.status} />
                      <span style={{ fontSize: 12, flex: 1, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>
                        {task.task_params.query ?? task.task_type}
                      </span>
                      <span style={{ fontSize: 11, color: "var(--color-text-tertiary)", flexShrink: 0 }}>
                        ${task.cost_so_far.toFixed(4)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Right: detail panel ── */}
        <div style={{ borderLeft: "0.5px solid var(--color-border-tertiary)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={panelHeaderStyle}>
            <p style={{ margin: 0, fontSize: 12, fontWeight: 500, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              {selected ? "Task detail" : "Inspect"}
            </p>
          </div>
          <div style={{ flex: 1, overflow: "hidden", padding: 16 }}>
            <DetailPanel task={selected} />
          </div>
        </div>

      </div>
      {apiOk === false && (
        <ApiUnreachableModal onRetry={() => { checkHealth(); fetchTasks(); fetchStats(); }} />
      )}
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const EmptyState: FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{
    background: "var(--color-background-primary)",
    border: "0.5px solid var(--color-border-tertiary)",
    borderRadius: "var(--border-radius-lg)",
    padding: "24px 20px", textAlign: "center",
    color: "var(--color-text-tertiary)", fontSize: 13,
  }}>
    {children}
  </div>
);