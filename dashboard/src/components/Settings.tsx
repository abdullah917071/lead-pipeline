"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Panel, Button, fmtINR, Toast, Spinner } from "./ui";
import { api } from "../lib/api";
import { Save, RotateCcw, Sliders } from "lucide-react";

const EDITABLE: { key: string; label: string; type: "number" | "text" | "bool" | "long" }[] = [
  { key: "min_amount_inr", label: "Min Deposit (₹)", type: "number" },
  { key: "max_amount_inr", label: "Max Deposit (₹)", type: "number" },
  { key: "payment_session_expiry_minutes", label: "Session Expiry (min)", type: "number" },
  { key: "upi_merchant_name", label: "UPI Merchant Name", type: "text" },
  { key: "wa_optin_template_name", label: "WA Opt-in Template", type: "text" },
  { key: "wa_optin_image_url", label: "WA Opt-in Image URL", type: "text" },
  { key: "razorpay_enabled", label: "Razorpay Enabled", type: "bool" },
  { key: "optin_body_template", label: "Opt-in Body", type: "long" },
  { key: "call_notice_template", label: "Call Notice", type: "long" },
  { key: "qr_caption_template", label: "QR Caption", type: "long" },
  { key: "dograh_trigger_path", label: "Dograh Trigger Path", type: "text" },
];

export default function SettingsSection() {
  const [settings, setSettings] = useState<Record<string, any>>({});
  const [overrides, setOverrides] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; tone: "ok" | "err" } | null>(null);
  const [drafts, setDrafts] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { const r = await api.settings(); setSettings(r.settings); setOverrides(r.overrides || {}); setErr(null); }
    catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  function setDraft(key: string, value: any) { setDrafts((d) => ({ ...d, [key]: value })); }
  async function save(key: string) {
    const value = drafts[key];
    if (value === undefined || value === settings[key]) { setToast({ msg: "No change to save", tone: "ok" }); setTimeout(() => setToast(null), 1600); return; }
    setBusy(true);
    try {
      const e = EDITABLE.find((x) => x.key === key);
      const v = e?.type === "number" ? Number(value) : value;
      await api.putSetting(key, v);
      setToast({ msg: `Saved ${key} ✓`, tone: "ok" });
      setDrafts((d) => { const n = { ...d }; delete n[key]; return n; });
      load();
    } catch (e: any) { setToast({ msg: "Error: " + e.message, tone: "err" }); }
    finally { setBusy(false); setTimeout(() => setToast(null), 2800); }
  }

  if (loading && Object.keys(settings).length === 0) return <Spinner />;
  if (err) return <div className="text-rose-400 p-8 text-sm">Error: {err}</div>;

  const dirty = Object.keys(drafts).length;

  return (
    <div className="space-y-4 fade-up">
      <Toast msg={toast?.msg || null} tone={toast?.tone} />
      <Panel
        title="Pipeline Settings"
        subtitle="Runtime-editable · persisted to pipeline_settings, falls back to config defaults"
        action={dirty > 0 ? <span className="pill bg-amber-500/15 text-amber-300">{dirty} unsaved</span>
          : <span className="pill bg-[var(--surface-2)] text-[var(--text-faint)]"><Sliders className="w-3 h-3" /> all saved</span>}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {EDITABLE.map((e) => {
            const current = settings[e.key];
            const isOverridden = e.key in overrides;
            const draft = drafts[e.key] ?? current ?? "";
            const changed = drafts[e.key] !== undefined && drafts[e.key] !== current;
            return (
              <div key={e.key} className={`rounded-lg p-3 border transition-colors ${changed ? "bg-indigo-500/[0.06] border-indigo-500/30" : "surface-2 border-[var(--border)]"}`}>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-[13px] text-[var(--text)] font-medium">{e.label}</label>
                  {isOverridden && <span className="pill bg-emerald-500/15 text-emerald-300">override</span>}
                </div>
                {e.type === "long" ? (
                  <textarea value={String(draft)} onChange={(ev) => setDraft(e.key, ev.target.value)} rows={2}
                    className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-2.5 py-1.5 text-[12px] text-[var(--text)] resize-none focus:border-indigo-500 outline-none" />
                ) : e.type === "bool" ? (
                  <select value={String(draft)} onChange={(ev) => setDraft(e.key, ev.target.value === "true")}
                    className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-2.5 h-8 text-[12px] text-[var(--text)] focus:border-indigo-500 outline-none">
                    <option value="true">true</option><option value="false">false</option>
                  </select>
                ) : (
                  <input type={e.type === "number" ? "number" : "text"} value={String(draft)} onChange={(ev) => setDraft(e.key, ev.target.value)}
                    className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-2.5 h-8 text-[12px] text-[var(--text)] focus:border-indigo-500 outline-none" />
                )}
                <div className="flex items-center justify-between mt-2">
                  <span className="text-[10px] text-[var(--text-faint)] font-mono truncate max-w-[55%]">{String(current)}</span>
                  <div className="flex gap-1.5">
                    {changed && <button onClick={() => setDrafts((d) => { const n = { ...d }; delete n[e.key]; return n; })} className="text-[var(--text-faint)] hover:text-[var(--text)]" title="Discard"><RotateCcw className="w-3.5 h-3.5" /></button>}
                    <Button size="xs" onClick={() => save(e.key)} disabled={busy || !changed}><Save className="w-3 h-3" /> Save</Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
