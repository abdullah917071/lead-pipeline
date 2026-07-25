"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Panel, Metric, Spinner, Empty } from "./ui";
import { api } from "../lib/api";
import { Activity, CheckCircle2, XCircle, Database, Server, KeyRound, MessageSquare, Bot, RefreshCw } from "lucide-react";

function svcIcon(name: string) {
  const n = name.toLowerCase();
  if (n.includes("db") || n.includes("postgres") || n.includes("sql")) return <Database className="w-4 h-4" />;
  if (n.includes("redis")) return <Server className="w-4 h-4" />;
  if (n.includes("razorpay") || n.includes("pay")) return <KeyRound className="w-4 h-4" />;
  if (n.includes("wa") || n.includes("whatsapp")) return <MessageSquare className="w-4 h-4" />;
  if (n.includes("dograh") || n.includes("call") || n.includes("voice")) return <Bot className="w-4 h-4" />;
  return <Server className="w-4 h-4" />;
}

export default function HealthSection() {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setHealth(await api.health()); setErr(null); }
    catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, [load]);

  if (loading && !health) return <Spinner label="Checking health…" />;
  if (err) return <div className="text-rose-400 p-8 text-sm">Error: {err}</div>;
  if (!health) return null;

  const services = health.services || {};
  const entries = Object.entries(services) as [string, any][];

  return (
    <div className="space-y-4 fade-up">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <Metric label="Status" value={health.status} accent="emerald" icon={<Activity className="w-4 h-4" />} />
        <Metric label="Min / Max Deposit" value={`${health.min_amount} / ${health.max_amount}`} accent="slate" />
        <Metric label="Razorpay" value={health.razorpay_configured ? "configured" : "missing"} accent={health.razorpay_configured ? "emerald" : "rose"} />
        <Metric label="WA Template" value={health.wa_template || "—"} accent="cyan" />
        <Metric label="Dograh Base" value={health.dograh_base || "—"} accent="cyan" />
        <Metric label="Generated" value={new Date(health.generated_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })} accent="slate" />
      </div>

      <Panel title="Services" subtitle="Backend service health" noPad action={
        <button onClick={load} className="text-[var(--text-faint)] hover:text-[var(--text)] p-1"><RefreshCw className="w-3.5 h-3.5" /></button>
      }>
        {entries.length === 0 ? <Empty text="No service details reported" icon={<Activity />} />
          : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-[var(--border)]">
              {entries.map(([name, s]: any) => {
                const ok = s?.status === "ok" || s?.healthy === true || s === "ok";
                const warn = s?.status === "degraded" || s?.status === "warn";
                const detail = typeof s === "object" ? (s.detail || s.message || "") : String(s);
                const color = ok ? "#22c55e" : warn ? "#f59e0b" : "#ef4444";
                return (
                  <div key={name} className="flex items-center gap-3 bg-[var(--surface)] px-4 py-3.5">
                    <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${color}1a`, color }}>
                      {svcIcon(name)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[13px] text-[var(--text)] font-medium capitalize">{name.replace(/_/g, " ")}</p>
                      <p className="text-[11px] text-[var(--text-faint)] truncate">{detail || (ok ? "operational" : "down")}</p>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {ok ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <XCircle className="w-4 h-4 text-rose-400" />}
                      <span className={`text-[10px] font-semibold uppercase ${ok ? "text-emerald-400" : warn ? "text-amber-400" : "text-rose-400"}`}>
                        {typeof s === "object" ? (s.status || (ok ? "ok" : "down")) : s}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
      </Panel>
    </div>
  );
}
