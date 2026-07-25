"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Panel, StatusPill, Button, fmtTime, fmtINR, fmtNum, Toast, Empty, Spinner } from "./ui";
import { api, LeadRow } from "../lib/api";
import { Search, Plus, X, Phone, MessageSquare, QrCode, CheckCircle, RefreshCw, ChevronRight } from "lucide-react";

const STATUSES = ["", "wa_sent", "wa_replied", "call_triggered", "call_completed", "awaiting_payment", "payment_received", "completed", "rejected", "cold"];

export default function LeadsSection() {
  const [leads, setLeads] = useState<LeadRow[]>([]);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; tone: "ok" | "err" } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setLeads(await api.leads(status || undefined, 200)); setErr(null); }
    catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }, [status]);
  useEffect(() => { load(); const t = setInterval(load, 6000); return () => clearInterval(t); }, [load]);

  async function openDetail(id: string) {
    setDetailId(id); setDetail(null);
    try { setDetail(await api.leadDetail(id)); } catch (e: any) { setToast({ msg: "Detail error: " + e.message, tone: "err" }); }
  }
  async function action(fn: () => Promise<any>, label: string) {
    setBusy(true);
    try { await fn(); setToast({ msg: label, tone: "ok" }); load(); if (detailId) openDetail(detailId); }
    catch (e: any) { setToast({ msg: "Error: " + e.message, tone: "err" }); }
    finally { setBusy(false); setTimeout(() => setToast(null), 2800); }
  }

  const filtered = query
    ? leads.filter((l) => l.phone.includes(query) || (l.name || "").toLowerCase().includes(query.toLowerCase()))
    : leads;

  return (
    <div className="space-y-4 fade-up">
      <Toast msg={toast?.msg || null} tone={toast?.tone} />

      <Panel noPad>
        <div className="flex flex-wrap items-center gap-2.5 p-3 border-b hairline">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-[var(--text-faint)] absolute left-3 top-1/2 -translate-y-1/2" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search phone or name…"
              className="bg-[var(--surface-2)] border border-[var(--border)] rounded-lg pl-9 pr-3 h-8 text-[13px] text-[var(--text)] placeholder:text-[var(--text-faint)] w-56 focus:border-indigo-500 outline-none" />
          </div>
          <select value={status} onChange={(e) => setStatus(e.target.value)}
            className="bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 h-8 text-[13px] text-[var(--text)] focus:border-indigo-500 outline-none">
            {STATUSES.map((s) => <option key={s} value={s}>{s ? s.replace(/_/g, " ") : "All statuses"}</option>)}
          </select>
          <Button variant="primary" onClick={() => action(() => api.ingest("+919****9999", "Test Lead"), "Ingested test lead")} disabled={busy}>
            <Plus className="w-3.5 h-3.5" /> New Lead
          </Button>
          <Button variant="ghost" size="sm" onClick={load} disabled={busy}><RefreshCw className="w-3.5 h-3.5" /></Button>
          <span className="text-xs text-[var(--text-faint)] ml-auto">{fmtNum(filtered.length)} shown</span>
        </div>

        {loading && leads.length === 0 ? <Spinner />
          : filtered.length === 0 ? <Empty text="No leads match" />
          : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--text-faint)] border-b hairline">
                    <th className="px-4 py-2.5 font-medium">Phone</th>
                    <th className="px-4 py-2.5 font-medium">Name</th>
                    <th className="px-4 py-2.5 font-medium">Status</th>
                    <th className="px-4 py-2.5 font-medium">Source</th>
                    <th className="px-4 py-2.5 font-medium">Updated</th>
                    <th className="px-4 py-2.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((l) => (
                    <tr key={l.id} className="border-b border-[var(--border)] hover:bg-white/[0.02] transition-colors">
                      <td className="px-4 py-3 font-mono text-[12px] text-[var(--text)]">{l.phone}</td>
                      <td className="px-4 py-3 text-[var(--text)]">{l.name || "—"}</td>
                      <td className="px-4 py-3"><StatusPill status={l.status} /></td>
                      <td className="px-4 py-3 text-[var(--text-dim)]">{l.source}</td>
                      <td className="px-4 py-3 text-[var(--text-faint)] text-[12px]">{fmtTime(l.updated_at)}</td>
                      <td className="px-4 py-3 text-right"><Button variant="ghost" size="xs" onClick={() => openDetail(l.id)}>Open <ChevronRight className="w-3.5 h-3.5" /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Panel>

      {/* Slide-over */}
      {detailId && (
        <div className="fixed inset-0 z-40 flex justify-end" onClick={() => { setDetailId(null); setDetail(null); }}>
          <div className="absolute inset-0 bg-black/60" />
          <div className="relative w-full max-w-md surface rounded-none sm:rounded-l-2xl overflow-y-auto fade-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b hairline sticky top-0 surface z-10">
              <h3 className="text-[15px] font-semibold">Lead Detail</h3>
              <button onClick={() => { setDetailId(null); setDetail(null); }} className="text-[var(--text-faint)] hover:text-[var(--text)]"><X className="w-5 h-5" /></button>
            </div>

            {!detail ? <Spinner />
              : (
                <div className="p-5 space-y-5">
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Phone" value={detail.phone} mono />
                    <Field label="Name" value={detail.name || "—"} />
                    <Field label="Status"><StatusPill status={detail.status} /></Field>
                    <Field label="Source" value={detail.source} />
                  </div>

                  <div>
                    <p className="text-[11px] uppercase tracking-wider text-[var(--text-faint)] mb-2">Manual Actions</p>
                    <div className="flex flex-wrap gap-2">
                      <Button variant="indigo" onClick={() => action(() => api.sendOptin(detail.id), "Opt-in sent ✓")} disabled={busy}><MessageSquare className="w-3.5 h-3.5" /> Opt-in</Button>
                      <Button variant="cyan" onClick={() => action(() => api.triggerCall(detail.id), "Call triggered ✓")} disabled={busy}><Phone className="w-3.5 h-3.5" /> Call</Button>
                      <Button variant="amber" onClick={() => action(() => api.resendQr(detail.id), "QR resent ✓")} disabled={busy}><QrCode className="w-3.5 h-3.5" /> Resend QR</Button>
                      <Button variant="emerald" onClick={() => action(() => api.markPayment(detail.id, 1, "admin-" + Date.now()), "Payment marked ✓")} disabled={busy}><CheckCircle className="w-3.5 h-3.5" /> Mark ₹1</Button>
                    </div>
                  </div>

                  {detail.sessions?.length > 0 && (
                    <Block title="Payment Sessions">
                      {detail.sessions.map((s: any) => (
                        <div key={s.ref_id} className="surface-2 rounded-lg p-3 mb-2 text-[12px] space-y-1.5">
                          <Row k="Amount" v={<span className="text-emerald-400">{fmtINR(s.amount)}</span>} />
                          <Row k="Status" v={s.status} />
                          <Row k="Gateway" v={s.gateway} />
                          <Row k="UPI" v={<span className="font-mono">{s.upi_id}</span>} />
                          {s.qr_image_url && (
                            <div className="mt-1">
                              {s.qr_image_url.startsWith("data:") ? <img src={s.qr_image_url} alt="QR" className="w-28 h-28 rounded-lg mx-auto" />
                                : <a href={s.qr_image_url} target="_blank" rel="noreferrer" className="text-cyan-400 underline">View QR</a>}
                            </div>
                          )}
                        </div>
                      ))}
                    </Block>
                  )}

                  {detail.provisioned && (
                    <Block title="Provisioned Account">
                      <div className="surface-2 rounded-lg p-3 text-[12px] space-y-1.5">
                        <Row k="User ID" v={<span className="font-mono text-[var(--text)]">{detail.provisioned.user_id}</span>} />
                        <Row k="Password" v={<span className="font-mono text-[var(--text)]">{detail.provisioned.password}</span>} />
                        <Row k="Balance" v={<span className="text-emerald-400">{fmtINR(detail.provisioned.initial_balance)}</span>} />
                      </div>
                    </Block>
                  )}

                  {detail.calls?.length > 0 && (
                    <Block title="Call Logs">
                      {detail.calls.map((c: any, i: number) => (
                        <div key={i} className="surface-2 rounded-lg px-3 py-2 text-[12px] mb-1 flex justify-between">
                          <span className="text-[var(--text-dim)]">{c.status}</span>
                          <span className="text-emerald-400">{c.amount ? fmtINR(c.amount) : "—"}</span>
                          <span className="text-[var(--text-faint)]">{fmtTime(c.created_at)}</span>
                        </div>
                      ))}
                    </Block>
                  )}

                  {!detail.sessions?.length && !detail.provisioned && !detail.calls?.length && (
                    <p className="text-[12px] text-[var(--text-faint)] text-center py-4">No sessions or calls yet.</p>
                  )}
                </div>
              )}
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, children, mono }: { label: string; value?: string; children?: React.ReactNode; mono?: boolean }) {
  return (
    <div className="surface-2 rounded-lg p-3">
      <p className="text-[10px] uppercase tracking-wider text-[var(--text-faint)] mb-1">{label}</p>
      <p className={`text-[13px] text-[var(--text)] ${mono ? "font-mono" : ""}`}>{children ?? value}</p>
    </div>
  );
}
function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (<div className="flex justify-between"><span className="text-[var(--text-faint)]">{k}</span><span className="text-[var(--text)]">{v}</span></div>);
}
function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (<div><p className="text-[11px] uppercase tracking-wider text-[var(--text-faint)] mb-2">{title}</p>{children}</div>);
}
