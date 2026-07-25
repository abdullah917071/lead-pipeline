"use client";

import React, { useState, useEffect } from "react";
import {
  LayoutDashboard, Users, CreditCard, PhoneCall, Settings as SettingsIcon,
  Activity, Workflow, RefreshCw, Radio, Bell,
} from "lucide-react";
import MonitorSection from "../components/Monitor";
import LeadsSection from "../components/Leads";
import PaymentsSection from "../components/Payments";
import CallsSection from "../components/Calls";
import SettingsSection from "../components/Settings";
import HealthSection from "../components/Health";

type Section = "monitor" | "leads" | "payments" | "calls" | "settings" | "health";

const NAV: { id: Section; label: string; icon: any }[] = [
  { id: "monitor", label: "Monitor", icon: LayoutDashboard },
  { id: "leads", label: "Leads", icon: Users },
  { id: "payments", label: "Payments", icon: CreditCard },
  { id: "calls", label: "Calls", icon: PhoneCall },
  { id: "settings", label: "Settings", icon: SettingsIcon },
  { id: "health", label: "Health", icon: Activity },
];

const TITLES: Record<Section, { title: string; sub: string }> = {
  monitor: { title: "Monitor", sub: "Real-time funnel, revenue and conversion health" },
  leads: { title: "Leads", sub: "Browse, inspect and manually drive each lead" },
  payments: { title: "Payments", sub: "Razorpay dynamic-QR collections and merchant rotation" },
  calls: { title: "Calls", sub: "Dograh AI outbound voice-call history" },
  settings: { title: "Settings", sub: "Runtime-editable pipeline configuration" },
  health: { title: "Health", sub: "Backend service status and integrations" },
};

function useClock() {
  const [now, setNow] = useState<string>("");
  useEffect(() => {
    const tick = () => setNow(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

export default function Dashboard() {
  const [active, setActive] = useState<Section>("monitor");
  const [live, setLive] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const clock = useClock();

  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)] flex">
      {/* Sidebar */}
      <aside className="w-[232px] shrink-0 border-r hairline bg-[var(--surface)]/60 flex flex-col sticky top-0 h-screen">
        <div className="h-16 flex items-center gap-2.5 px-5 border-b hairline">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-indigo-900/30">
            <Workflow className="w-4 h-4 text-white" />
          </div>
          <div className="leading-none">
            <p className="font-semibold text-[14px] tracking-tight">LeadFlow</p>
            <p className="text-[10px] text-[var(--text-faint)] mt-0.5">Sai Bhai Control</p>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {NAV.map((n) => {
            const Icon = n.icon;
            const on = active === n.id;
            return (
              <button key={n.id} onClick={() => setActive(n.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors ${
                  on ? "bg-indigo-500/10 text-indigo-300" : "text-[var(--text-dim)] hover:text-[var(--text)] hover:bg-white/[0.03]"
                }`}>
                <Icon className={`w-4 h-4 ${on ? "text-indigo-400" : "text-[var(--text-faint)]"}`} />
                {n.label}
              </button>
            );
          })}
        </nav>

        <div className="p-4 border-t hairline flex items-center gap-2 text-[10px] text-[var(--text-faint)]">
          <span className={`w-1.5 h-1.5 rounded-full ${live ? "bg-emerald-400 pulse-dot" : "bg-[var(--text-faint)]"}`} />
          <span>live · v3 pipeline</span>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Top bar */}
        <header className="h-16 shrink-0 border-b hairline bg-[var(--surface)]/60 backdrop-blur-sm flex items-center justify-between px-6 sticky top-0 z-20">
          <div>
            <h1 className="text-[15px] font-semibold tracking-tight">{TITLES[active].title}</h1>
            <p className="text-[11px] text-[var(--text-faint)]">{TITLES[active].sub}</p>
          </div>
          <div className="flex items-center gap-2.5">
            <span className="hidden sm:flex items-center gap-2 text-[12px] text-[var(--text-faint)] font-mono tabular-nums px-3 h-8 rounded-lg surface-2 border border-[var(--border)]">
              <span className={`w-1.5 h-1.5 rounded-full ${live ? "bg-emerald-400 pulse-dot" : "bg-[var(--text-faint)]"}`} />
              {clock}
            </span>
            <button onClick={() => setLive((v) => !v)}
              className={`flex items-center gap-1.5 h-8 px-3 rounded-lg text-[12px] font-medium border transition-colors ${
                live ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "text-[var(--text-dim)] border-[var(--border)]"
              }`}>
              <Radio className="w-3.5 h-3.5" /> {live ? "Live" : "Paused"}
            </button>
            <button onClick={() => setRefreshKey((k) => k + 1)} className="h-8 w-8 grid place-items-center rounded-lg surface-2 border border-[var(--border)] text-[var(--text-dim)] hover:text-[var(--text)] transition-colors">
              <RefreshCw className="w-4 h-4" />
            </button>
            <button className="h-8 w-8 grid place-items-center rounded-lg surface-2 border border-[var(--border)] text-[var(--text-dim)] hover:text-[var(--text)] transition-colors relative">
              <Bell className="w-4 h-4" /><span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-indigo-400" />
            </button>
          </div>
        </header>

        <main className="flex-1 p-6 overflow-y-auto">
          {active === "monitor" && <MonitorSection key={`m-${refreshKey}`} />}
          {active === "leads" && <LeadsSection key={`l-${refreshKey}`} />}
          {active === "payments" && <PaymentsSection key={`p-${refreshKey}`} />}
          {active === "calls" && <CallsSection key={`c-${refreshKey}`} />}
          {active === "settings" && <SettingsSection key={`s-${refreshKey}`} />}
          {active === "health" && <HealthSection key={`h-${refreshKey}`} />}
        </main>
      </div>
    </div>
  );
}
