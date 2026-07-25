// API client for the Lead Pipeline admin control panel.
// All calls go to /api/admin/* which Next.js proxies to the FastAPI backend (:9000).

const BASE = "/api/admin";

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export interface MonitorTotals {
  leads_total: number;
  leads_24h: number;
  leads_7d: number;
  completed: number;
  awaiting_payment: number;
  active_calls: number;
  calls_completed: number;
}

export interface Monitor {
  funnel: Record<string, number>;
  totals: MonitorTotals;
  revenue: { total: number; "24h": number; "7d": number };
  generated_at: string;
}

export interface LeadRow {
  id: string;
  phone: string;
  name: string | null;
  status: string;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface Setting {
  key: string;
  value: any;
}

export const api = {
  monitor: () => req<Monitor>("/monitor"),
  revenueTimeseries: (days = 7) =>
    req<{ series: { date: string; revenue: number }[] }>(`/revenue-timeseries?days=${days}`),
  funnelTimeseries: (days = 7) =>
    req<{ series: { date: string; leads: number }[] }>(`/funnel-timeseries?days=${days}`),
  settings: () => req<{ settings: Record<string, any>; defaults: Record<string, any>; overrides?: Record<string, any> }>("/settings"),
  putSetting: (key: string, value: any) =>
    req("/settings", {
      method: "PUT",
      body: JSON.stringify({ key, value, updated_by: "admin" }),
    }),
  leads: (status?: string, limit = 100, offset = 0) =>
    req<LeadRow[]>(`/leads?limit=${limit}&offset=${offset}${status ? `&status=${status}` : ""}`),
  leadDetail: (id: string) => req<any>(`/leads/${id}/detail`),
  sendOptin: (id: string) => req(`/leads/${id}/send-optin`, { method: "POST" }),
  triggerCall: (id: string) => req(`/leads/${id}/trigger-call`, { method: "POST" }),
  resendQr: (id: string, amount?: number) =>
    req(`/leads/${id}/resend-qr${amount ? `?amount=${amount}` : ""}`, { method: "POST" }),
  // Backend expects amount + utr as query params, not JSON body.
  markPayment: (id: string, amount: number, utr: string) =>
    req(`/leads/${id}/mark-payment?amount=${encodeURIComponent(amount)}&utr=${encodeURIComponent(utr)}`, {
      method: "POST",
    }),
  advance: (id: string, status: string) =>
    req(`/leads/${id}/advance`, { method: "POST", body: JSON.stringify({ status }) }),
  ingest: (phone: string, name: string) =>
    req("/leads/ingest", {
      method: "POST",
      body: JSON.stringify({ phone, name, source: "admin" }),
    }),
  upiAccounts: () => req<any>("/upi/accounts"),
  rotateUpi: () => req("/upi/rotate", { method: "POST" }),
  payments: (limit = 50) => req<any[]>(`/payments?limit=${limit}`),
  calls: (limit = 50) => req<any[]>(`/calls?limit=${limit}`),
  dograhWorkflow: () => req<any>("/dograh/workflow"),
  health: () => req<any>("/health-detail"),
};
