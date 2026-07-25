"use client";

import React, { useEffect, useState } from "react";
import { Panel, Metric, Ring, fmtINR, fmtNum, Empty, Spinner } from "./ui";
import { api, Monitor } from "../lib/api";
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from "recharts";
import { Users, Clock, CheckCircle2, Wallet, IndianRupee, TrendingUp, PhoneCall, ArrowUpRight, ArrowDownRight } from "lucide-react";

const STAGES = [
  ["pending_wa_optin", "Pending Opt-in", "#64748b"],
  ["wa_sent", "WhatsApp Sent", "#6366f1"],
  ["wa_replied", "WhatsApp Replied", "#818cf8"],
  ["call_triggered", "Call Triggered", "#06b6d4"],
  ["call_completed", "Call Completed", "#22d3ee"],
  ["qr_generated", "QR Generated", "#f59e0b"],
  ["awaiting_payment", "Awaiting Payment", "#fb923c"],
  ["payment_received", "Payment Received", "#34d399"],
  ["credentials_delivered", "Credentials Sent", "#10b981"],
  ["completed", "Completed", "#22c55e"],
  ["rejected", "Rejected", "#ef4444"],
  ["cold", "Cold", "#94a3b8"],
] as const;

export default function MonitorSection() {
  const [data, setData] = useState<Monitor | null>(null);
  const [rev, setRev] = useState<{ date: string; revenue: number }[]>([]);
  const [funnel, setFunnel] = useState<{ date: string; leads: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [at, setAt] = useState<string | null>(null);

  async function load() {
    try {
      const [m, r, f] = await Promise.all([api.monitor(), api.revenueTimeseries(7), api.funnelTimeseries(7)]);
      setData(m); setRev(r.series); setFunnel(f.series);
      setAt(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
      setErr(null);
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, []);

  if (loading && !data) return <Spinner label="Loading monitor…" />;
  if (err) return <div className="text-rose-400 p-8 text-sm">Error: {err}</div>;
  if (!data) return null;

  const t = data.totals;
  const conv = t.leads_total > 0 ? (t.completed / t.leads_total) * 100 : 0;
  const maxF = Math.max(1, ...Object.values(data.funnel));
  const revUp = (data.revenue["7d"] > 0);

  return (
    <div className="space-y-5 fade-up">
      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <Metric label="Total Leads" value={fmtNum(t.leads_total)} accent="indigo" icon={<Users className="w-4 h-4" />} hint={`${fmtNum(t.leads_7d)} in 7 days`} />
        <Metric label="New (24h)" value={fmtNum(t.leads_24h)} accent="cyan" icon={<Clock className="w-4 h-4" />} delta={{ value: "live", positive: true }} />
        <Metric label="Converted" value={fmtNum(t.completed)} accent="emerald" icon={<CheckCircle2 className="w-4 h-4" />} hint="full funnel" />
        <Metric label="Awaiting Pay" value={fmtNum(t.awaiting_payment)} accent="amber" icon={<Wallet className="w-4 h-4" />} />
        <Metric label="Revenue (total)" value={fmtINR(data.revenue.total)} accent="emerald" icon={<IndianRupee className="w-4 h-4" />} />
        <Metric label="Revenue (7d)" value={fmtINR(data.revenue["7d"])} accent="cyan" icon={<TrendingUp className="w-4 h-4" />} delta={{ value: fmtINR(data.revenue["7d"]), positive: revUp }} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Conversion ring */}
        <Panel title="Conversion Rate" subtitle="Leads → delivered accounts" className="flex flex-col items-center justify-center">
          <div className="py-4"><Ring value={conv} /></div>
          <div className="grid grid-cols-2 gap-3 w-full mt-2">
            <div className="surface-2 rounded-lg p-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">Active Calls</p>
              <p className="text-lg font-semibold text-cyan-300">{t.active_calls}</p>
            </div>
            <div className="surface-2 rounded-lg p-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">Calls Done</p>
              <p className="text-lg font-semibold text-violet-300">{t.calls_completed}</p>
            </div>
          </div>
        </Panel>

        {/* Funnel table */}
        <Panel title="Funnel by Stage" subtitle="Live lead counts" className="lg:col-span-2" noPad>
          <div className="px-3 py-2 divide-y divide-[var(--border)]">
            {STAGES.map(([key, label, color]) => {
              const count = data.funnel[key] || 0;
              const pct = (count / maxF) * 100;
              return (
                <div key={key} className="flex items-center gap-3 px-2 py-2.5">
                  <span className="w-28 shrink-0 text-[13px] text-[var(--text-dim)]">{label}</span>
                  <div className="flex-1 h-2 rounded-full bg-[var(--surface-2)] overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
                  </div>
                  <span className="w-10 text-right text-[13px] font-semibold tabular-nums text-[var(--text)]">{count}</span>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Revenue — Last 7 Days" subtitle="Realized revenue (₹)">
          {rev.some((r) => r.revenue > 0) ? (
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={rev} margin={{ top: 8, right: 6, left: -16, bottom: 0 }}>
                <defs>
                  <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22c55e" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="date" tickFormatter={(d) => (d ? d.slice(5) : "")} axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} width={44} />
                <Tooltip formatter={(v: any) => ["₹" + v, "Revenue"]} />
                <Area type="monotone" dataKey="revenue" stroke="#22c55e" strokeWidth={2.5} fill="url(#rev)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : <Empty text="No revenue in last 7 days" />}
        </Panel>

        <Panel title="Lead Intake — Last 7 Days" subtitle="New leads per day">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={funnel} margin={{ top: 8, right: 6, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="ld" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" />
                  <stop offset="100%" stopColor="#06b6d4" />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="date" tickFormatter={(d) => (d ? d.slice(5) : "")} axisLine={false} tickLine={false} />
              <YAxis axisLine={false} tickLine={false} width={44} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(99,102,241,0.06)" }} />
              <Bar dataKey="leads" radius={[5, 5, 0, 0]}>
                {funnel.map((_, i) => <Cell key={i} fill="url(#ld)" />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      <p className="text-[11px] text-[var(--text-faint)] text-right">Auto-refresh · updated {at}</p>
    </div>
  );
}
