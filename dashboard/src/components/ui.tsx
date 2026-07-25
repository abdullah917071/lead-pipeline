"use client";

import React from "react";

/* ---------------- Surfaces & primitives ---------------- */

export function Panel({
  children, className = "", title, subtitle, action, noPad,
}: {
  children: React.ReactNode; className?: string;
  title?: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode;
  noPad?: boolean;
}) {
  return (
    <section className={`surface ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 px-5 py-4 border-b hairline">
          <div>
            {title && <h3 className="text-[13px] font-semibold text-[var(--text)]">{title}</h3>}
            {subtitle && <p className="text-xs text-[var(--text-faint)] mt-0.5">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={noPad ? "" : "p-5"}>{children}</div>
    </section>
  );
}

/* ---------------- KPI metric ---------------- */

export function Metric({
  label, value, delta, accent = "indigo", icon, hint,
}: {
  label: string; value: React.ReactNode; delta?: { value: string; positive: boolean };
  accent?: "indigo" | "emerald" | "cyan" | "amber" | "rose" | "violet" | "slate";
  icon?: React.ReactNode; hint?: string;
}) {
  const accentText: Record<string, string> = {
    indigo: "text-indigo-400", emerald: "text-emerald-400", cyan: "text-cyan-400",
    amber: "text-amber-400", rose: "text-rose-400", violet: "text-violet-400", slate: "text-slate-200",
  };
  const accentBg: Record<string, string> = {
    indigo: "bg-indigo-500/10 text-indigo-300", emerald: "bg-emerald-500/10 text-emerald-300",
    cyan: "bg-cyan-500/10 text-cyan-300", amber: "bg-amber-500/10 text-amber-300",
    rose: "bg-rose-500/10 text-rose-300", violet: "bg-violet-500/10 text-violet-300",
    slate: "bg-slate-500/10 text-slate-200",
  };
  return (
    <div className="surface p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-faint)]">{label}</span>
        {icon && <span className={`w-7 h-7 rounded-lg flex items-center justify-center ${accentBg[accent]}`}>{icon}</span>}
      </div>
      <div className="flex items-end justify-between gap-2">
        <span className={`text-[26px] leading-none font-semibold tabular-nums ${accentText[accent]}`}>{value}</span>
        {delta && (
          <span className={`text-[11px] font-semibold ${delta.positive ? "text-emerald-400" : "text-rose-400"}`}>
            {delta.positive ? "▲" : "▼"} {delta.value}
          </span>
        )}
      </div>
      {hint && <span className="text-[11px] text-[var(--text-faint)]">{hint}</span>}
    </div>
  );
}

/* ---------------- Status pill ---------------- */

const STATUS_STYLE: Record<string, string> = {
  pending_wa_optin: "bg-slate-500/15 text-slate-300",
  wa_sent: "bg-indigo-500/15 text-indigo-300",
  wa_replied: "bg-indigo-400/15 text-indigo-200",
  call_triggered: "bg-cyan-500/15 text-cyan-300",
  call_completed: "bg-cyan-400/15 text-cyan-200",
  call_failed: "bg-rose-500/15 text-rose-300",
  amount_confirmed: "bg-amber-500/15 text-amber-300",
  qr_generated: "bg-amber-400/15 text-amber-200",
  awaiting_payment: "bg-amber-500/15 text-amber-300",
  payment_received: "bg-emerald-500/15 text-emerald-300",
  payment_verified: "bg-emerald-400/15 text-emerald-200",
  account_created: "bg-emerald-500/15 text-emerald-300",
  credentials_delivered: "bg-emerald-500/15 text-emerald-300",
  completed: "bg-emerald-500/15 text-emerald-300",
  cold: "bg-slate-500/15 text-slate-400",
  rejected: "bg-rose-500/15 text-rose-300",
  payment_failed: "bg-rose-500/15 text-rose-300",
  manual_review: "bg-violet-500/15 text-violet-300",
};

export function StatusPill({ status }: { status: string }) {
  const cls = STATUS_STYLE[status] || "bg-slate-600/15 text-slate-300";
  return (
    <span className={`pill ${cls}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {status.replace(/_/g, " ")}
    </span>
  );
}

/* ---------------- Buttons ---------------- */

export function Button({
  children, onClick, variant = "primary", size = "sm", disabled, className = "",
}: {
  children: React.ReactNode; onClick?: () => void;
  variant?: "primary" | "ghost" | "danger" | "emerald" | "amber" | "cyan" | "indigo" | "subtle";
  size?: "sm" | "xs"; disabled?: boolean; className?: string;
}) {
  const variants: Record<string, string> = {
    primary: "bg-indigo-600 hover:bg-indigo-500 text-white border border-indigo-500",
    indigo: "bg-indigo-600 hover:bg-indigo-500 text-white border border-indigo-500",
    emerald: "bg-emerald-600 hover:bg-emerald-500 text-white border border-emerald-500",
    amber: "bg-amber-500 hover:bg-amber-400 text-black border border-amber-400",
    cyan: "bg-cyan-600 hover:bg-cyan-500 text-white border border-cyan-500",
    danger: "bg-rose-600 hover:bg-rose-500 text-white border border-rose-500",
    ghost: "bg-transparent hover:bg-white/5 text-[var(--text-dim)] border border-[var(--border)]",
    subtle: "bg-[var(--surface-2)] hover:bg-[#1a1e27] text-[var(--text)] border border-[var(--border)]",
  };
  const sizes = { sm: "h-8 px-3.5 text-[13px]", xs: "h-7 px-2.5 text-xs" };
  return (
    <button
      onClick={onClick} disabled={disabled}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:opacity-40 disabled:pointer-events-none ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {children}
    </button>
  );
}

/* ---------------- Feedback ---------------- */

export function Toast({ msg, tone = "ok" }: { msg: string | null; tone?: "ok" | "err" }) {
  if (!msg) return null;
  return (
    <div className={`fixed bottom-6 right-6 z-50 surface-2 rounded-xl px-4 py-3 text-sm fade-up border ${tone === "ok" ? "border-emerald-500/30" : "border-rose-500/30"} ${tone === "ok" ? "text-emerald-300" : "text-rose-300"}`}>
      {msg}
    </div>
  );
}

export function Empty({ text = "No data", icon }: { text?: string; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-[var(--text-faint)]">
      <div className="w-11 h-11 rounded-full bg-[var(--surface-2)] border border-[var(--border)] flex items-center justify-center text-[var(--text-faint)] mb-3 text-lg">
        {icon || "∅"}
      </div>
      <p className="text-[13px]">{text}</p>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-[var(--text-faint)] gap-3">
      <div className="w-5 h-5 border-2 border-[var(--border-strong)] border-t-indigo-400 rounded-full animate-spin" />
      {label && <span className="text-xs">{label}</span>}
    </div>
  );
}

/* ---------------- Progress ring ---------------- */

export function Ring({ value, size = 128, stroke = 10, color = "#22c55e" }: {
  value: number; size?: number; stroke?: number; color?: string;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const off = c - (Math.min(100, Math.max(0, value)) / 100) * c;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off} className="transition-all duration-700" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-semibold text-[var(--text)] tabular-nums">{value.toFixed(1)}%</span>
        <span className="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">conversion</span>
      </div>
    </div>
  );
}

/* ---------------- Formatters ---------------- */

export function fmtINR(n: number) {
  return "₹" + (n || 0).toLocaleString("en-IN");
}
export function fmtNum(n: number) {
  return (n || 0).toLocaleString("en-IN");
}
export function fmtTime(iso?: string) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}
