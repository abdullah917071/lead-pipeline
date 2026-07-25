"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Panel, Metric, fmtTime, fmtNum, Empty, Spinner } from "./ui";
import { api } from "../lib/api";
import { PhoneCall, CheckCircle2, XCircle, Timer, RefreshCw } from "lucide-react";

export default function CallsSection() {
  const [calls, setCalls] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setCalls(await api.calls(100)); setErr(null); }
    catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 6000); return () => clearInterval(t); }, [load]);

  const ok = (s: string) => ["completed", "success", "answered"].includes(s);
  const done = calls.filter((c) => ok(c.status)).length;
  const failed = calls.filter((c) => !ok(c.status)).length;
  const totalDur = calls.reduce((s, c) => s + (c.duration || 0), 0);

  return (
    <div className="space-y-4 fade-up">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Metric label="Total Calls" value={fmtNum(calls.length)} accent="slate" icon={<PhoneCall className="w-4 h-4" />} />
        <Metric label="Completed" value={fmtNum(done)} accent="emerald" icon={<CheckCircle2 className="w-4 h-4" />} />
        <Metric label="Failed / Missed" value={fmtNum(failed)} accent="rose" icon={<XCircle className="w-4 h-4" />} />
        <Metric label="Talk Time" value={`${Math.round(totalDur / 60)}m`} accent="cyan" icon={<Timer className="w-4 h-4" />} />
      </div>

      <Panel title="Call Logs" subtitle="Dograh AI voice calls (most recent first)" noPad action={
        <button onClick={load} className="text-[var(--text-faint)] hover:text-[var(--text)] p-1"><RefreshCw className="w-3.5 h-3.5" /></button>
      }>
        {loading && calls.length === 0 ? <Spinner />
          : calls.length === 0 ? <Empty text="No calls placed yet" icon={<PhoneCall />} />
          : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--text-faint)] border-b hairline">
                    <th className="px-4 py-2.5 font-medium">Run ID</th>
                    <th className="px-4 py-2.5 font-medium">Status</th>
                    <th className="px-4 py-2.5 font-medium">Amount</th>
                    <th className="px-4 py-2.5 font-medium">Duration</th>
                    <th className="px-4 py-2.5 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.map((c, i) => {
                    const good = ok(c.status);
                    return (
                      <tr key={c.run_id || i} className="border-b border-[var(--border)] hover:bg-white/[0.02] transition-colors">
                        <td className="px-4 py-3 font-mono text-[12px] text-[var(--text-dim)]">{(c.run_id || "").slice(0, 14)}</td>
                        <td className="px-4 py-3">
                          <span className={`pill ${good ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"}`}>
                            {good ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}{c.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-emerald-400">{c.amount ? `₹${c.amount}` : "—"}</td>
                        <td className="px-4 py-3 text-[var(--text-dim)]">{c.duration ? `${c.duration}s` : "—"}</td>
                        <td className="px-4 py-3 text-[var(--text-faint)] text-[12px]">{fmtTime(c.created_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
      </Panel>
    </div>
  );
}
