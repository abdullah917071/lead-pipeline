"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Panel, Metric, Button, fmtINR, fmtTime, fmtNum, Toast, Empty, Spinner } from "./ui";
import { api } from "../lib/api";
import { IndianRupee, CheckCircle2, Clock, QrCode, RotateCw, RefreshCw } from "lucide-react";

export default function PaymentsSection() {
  const [payments, setPayments] = useState<any[]>([]);
  const [upi, setUpi] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; tone: "ok" | "err" } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { const [p, u] = await Promise.all([api.payments(100), api.upiAccounts()]); setPayments(p); setUpi(u); setErr(null); }
    catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 6000); return () => clearInterval(t); }, [load]);

  async function rotate() {
    setBusy(true);
    try { await api.rotateUpi(); setToast({ msg: "UPI merchant rotated ✓", tone: "ok" }); load(); }
    catch (e: any) { setToast({ msg: "Rotate error: " + e.message, tone: "err" }); }
    finally { setBusy(false); setTimeout(() => setToast(null), 2800); }
  }

  const paid = payments.filter((p) => p.status === "paid");
  const pending = payments.filter((p) => p.status !== "paid");
  const totalPaid = paid.reduce((s, p) => s + (p.amount || 0), 0);
  const active = upi?.accounts?.find((a: any) => a.id === upi.active_account_id);

  return (
    <div className="space-y-4 fade-up">
      <Toast msg={toast?.msg || null} tone={toast?.tone} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Metric label="Collected" value={fmtINR(totalPaid)} accent="emerald" icon={<IndianRupee className="w-4 h-4" />} hint="via Razorpay" />
        <Metric label="Paid Sessions" value={fmtNum(paid.length)} accent="cyan" icon={<CheckCircle2 className="w-4 h-4" />} />
        <Metric label="Pending / Open" value={fmtNum(pending.length)} accent="amber" icon={<Clock className="w-4 h-4" />} />
        <Metric label="Active UPI" value={active?.display_name || "—"} accent="slate" icon={<QrCode className="w-4 h-4" />} />
      </div>

      {upi && (
        <Panel title="Razorpay UPI Merchants" subtitle="Underlying UPI handles for dynamic QR" action={
          <Button variant="subtle" size="sm" onClick={rotate} disabled={busy}><RotateCw className="w-3.5 h-3.5" /> Rotate</Button>
        }>
          <div className="space-y-2.5">
            {upi.accounts.map((a: any) => (
              <div key={a.id} className={`flex items-center justify-between rounded-lg px-4 py-3 ${a.id === upi.active_account_id ? "bg-emerald-500/5 border border-emerald-500/20" : "surface-2 border border-[var(--border)]"}`}>
                <div className="flex items-center gap-3">
                  <span className={`w-2.5 h-2.5 rounded-full ${a.id === upi.active_account_id ? "bg-emerald-400 pulse-dot" : "bg-[var(--text-faint)]"}`} />
                  <div>
                    <p className="text-[13px] text-[var(--text)] font-medium">{a.display_name}</p>
                    <p className="font-mono text-[11px] text-[var(--text-faint)]">{a.upi_id}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-[12px] text-[var(--text)]">{fmtINR(a.current_volume)} <span className="text-[var(--text-faint)]">/ {fmtINR(a.daily_cap)}</span></p>
                  <p className="text-[10px] text-[var(--text-faint)] uppercase tracking-wide">{a.is_active ? "active" : "inactive"} · {a.is_enabled ? "enabled" : "disabled"}</p>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title="Payment Sessions" subtitle="Razorpay dynamic-QR payments (most recent first)" noPad action={
        <Button variant="ghost" size="sm" onClick={load} disabled={busy}><RefreshCw className="w-3.5 h-3.5" /></Button>
      }>
        {loading && payments.length === 0 ? <Spinner />
          : payments.length === 0 ? <Empty text="No payment sessions yet" icon={<QrCode />} />
          : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--text-faint)] border-b hairline">
                    <th className="px-4 py-2.5 font-medium">Ref</th>
                    <th className="px-4 py-2.5 font-medium">Amount</th>
                    <th className="px-4 py-2.5 font-medium">Status</th>
                    <th className="px-4 py-2.5 font-medium">Gateway</th>
                    <th className="px-4 py-2.5 font-medium">QR</th>
                    <th className="px-4 py-2.5 font-medium">UTR</th>
                    <th className="px-4 py-2.5 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((p) => (
                    <tr key={p.ref_id} className="border-b border-[var(--border)] hover:bg-white/[0.02] transition-colors">
                      <td className="px-4 py-3 font-mono text-[12px] text-[var(--text-dim)]">{p.ref_id?.slice(0, 12)}</td>
                      <td className="px-4 py-3 text-emerald-400 font-medium">{fmtINR(p.amount)}</td>
                      <td className="px-4 py-3">
                        <span className={`pill ${p.status === "paid" ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300"}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${p.status === "paid" ? "bg-emerald-400" : "bg-amber-400"}`} />{p.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-[var(--text-dim)]">{p.gateway || "razorpay"}</td>
                      <td className="px-4 py-3">
                        {p.qr_image_url ? (p.qr_image_url.startsWith("data:") ? <img src={p.qr_image_url} alt="QR" className="w-9 h-9 rounded-md" />
                          : <a href={p.qr_image_url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline text-[12px]">view</a>) : "—"}
                      </td>
                      <td className="px-4 py-3 font-mono text-[12px] text-[var(--text-dim)]">{p.utr || "—"}</td>
                      <td className="px-4 py-3 text-[var(--text-faint)] text-[12px]">{fmtTime(p.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Panel>
    </div>
  );
}
