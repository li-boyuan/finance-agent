"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { fmtCurrency, fmtPct, colorClass } from "@/components/portfolio/grouping";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface UnderlyingRow {
  underlying: string;
  spot: number | null;
  stock_shares: number;
  option_value: number;
  leg_count: number;
  net_share_delta: number | null;
  delta_dollars: number | null;
  delta_partial: boolean;
}

interface Expiration {
  expiry: string;
  dte: number | null;
  leg_count: number;
  net_value: number;
  underlyings: string[];
}

interface FlagLeg {
  symbol: string;
  name: string;
  underlying: string;
  option_type: "C" | "P";
  strike: number;
  expiry: string;
  dte: number | null;
  quantity: number;
  is_short: boolean;
  moneyness: string | null;
  value: number;
  assignment_risk: boolean;
  near_expiry: boolean;
  total_return_pct: number;
}

interface Analytics {
  as_of: string;
  has_greeks: boolean;
  totals: { option_value: number; leg_count: number; near_expiry: number; assignment_risk: number };
  underlyings: UnderlyingRow[];
  expirations: Expiration[];
  flags: FlagLeg[];
}

function fmtExpiry(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" });
}

function fmtShares(n: number) {
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export default function OptionsPage() {
  const router = useRouter();
  const supabase = createClient();
  const [token, setToken] = useState("");
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
      if (!session) {
        router.push("/login");
        return;
      }
      setToken(session.access_token);
    });
    return () => subscription.unsubscribe();
  }, [router, supabase]);

  const fetchData = useCallback(
    async (showSpinner = false) => {
      if (!token) return;
      if (showSpinner) setRefreshing(true);
      setError(null);
      try {
        const res = await fetch(`${API_URL}/api/options/analytics`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setData(await res.json());
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [token],
  );

  useEffect(() => {
    if (token) fetchData();
  }, [token, fetchData]);

  if (loading && !data) {
    return <div className="h-full flex items-center justify-center text-gray-400">Loading options…</div>;
  }
  if (!data) {
    return <div className="h-full flex items-center justify-center text-red-600">{error || "Could not load options analytics."}</div>;
  }

  const empty = data.totals.leg_count === 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold">Options</h1>
            <p className="text-sm text-gray-500 mt-1">
              {data.totals.leg_count} option leg{data.totals.leg_count === 1 ? "" : "s"} ·
              delta-adjusted exposure, expirations &amp; risk
            </p>
          </div>
          <button
            onClick={() => fetchData(true)}
            disabled={refreshing}
            className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition"
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            Couldn’t refresh: {error}
          </div>
        )}

        {empty ? (
          <div className="border border-gray-200 rounded-2xl p-12 text-center text-gray-500">
            No option positions. Sync IBKR or add options on the Holdings page.
          </div>
        ) : (
          <>
            {!data.has_greeks && (
              <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                Delta-adjusted exposure needs IBKR model greeks. Apply migration{" "}
                <code className="font-mono">006_holdings_greeks.sql</code> and re-sync IBKR to populate it.
                Expirations, moneyness, and risk flags below already work.
              </div>
            )}

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              <StatCard label="Option Value (net)" value={fmtCurrency(data.totals.option_value)} />
              <StatCard label="Legs" value={String(data.totals.leg_count)} />
              <StatCard
                label="Expiring ≤7d"
                value={String(data.totals.near_expiry)}
                color={data.totals.near_expiry ? "text-amber-600" : undefined}
              />
              <StatCard
                label="Assignment risk"
                value={String(data.totals.assignment_risk)}
                color={data.totals.assignment_risk ? "text-red-600" : undefined}
              />
            </div>

            <Section title="Exposure by underlying">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr className="text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                    <th className="px-4 py-3">Underlying</th>
                    <th className="px-4 py-3 text-right">Spot</th>
                    <th className="px-4 py-3 text-right">Net Δ (sh)</th>
                    <th className="px-4 py-3 text-right">Δ$ exposure</th>
                    <th className="px-4 py-3 text-right">Option value</th>
                    <th className="px-4 py-3 text-right">Legs</th>
                  </tr>
                </thead>
                <tbody>
                  {data.underlyings.map((u) => (
                    <tr key={u.underlying} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">
                        {u.underlying}
                        {u.stock_shares !== 0 && (
                          <span className="ml-2 text-xs text-gray-400">+{fmtShares(u.stock_shares)} sh</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">{u.spot != null ? fmtCurrency(u.spot) : "—"}</td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {u.net_share_delta != null ? fmtShares(u.net_share_delta) : "—"}
                        {u.delta_partial && <span className="text-amber-500" title="some legs missing greeks">*</span>}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {u.delta_dollars != null ? fmtCurrency(u.delta_dollars) : "—"}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">{fmtCurrency(u.option_value)}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-500">{u.leg_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.underlyings.some((u) => u.delta_partial) && (
                <div className="px-4 py-2 text-xs text-gray-400">* net delta is partial — some legs are missing greeks.</div>
              )}
            </Section>

            <Section title="Expirations">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr className="text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                    <th className="px-4 py-3">Expiry</th>
                    <th className="px-4 py-3 text-right">DTE</th>
                    <th className="px-4 py-3 text-right">Legs</th>
                    <th className="px-4 py-3 text-right">Net value</th>
                    <th className="px-4 py-3">Tickers</th>
                  </tr>
                </thead>
                <tbody>
                  {data.expirations.map((e) => (
                    <tr key={e.expiry} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">{fmtExpiry(e.expiry)}</td>
                      <td className={`px-4 py-3 text-right tabular-nums ${e.dte != null && e.dte <= 7 ? "text-amber-600 font-medium" : "text-gray-600"}`}>
                        {e.dte != null ? `${e.dte}d` : "—"}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-500">{e.leg_count}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{fmtCurrency(e.net_value)}</td>
                      <td className="px-4 py-3 text-xs text-gray-500 truncate max-w-[280px]">{e.underlyings.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>

            {data.flags.length > 0 && (
              <Section title="Risk flags">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                      <th className="px-4 py-3">Contract</th>
                      <th className="px-4 py-3">Flags</th>
                      <th className="px-4 py-3 text-right">DTE</th>
                      <th className="px-4 py-3 text-right">Qty</th>
                      <th className="px-4 py-3 text-right">Value</th>
                      <th className="px-4 py-3 text-right">Return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.flags.map((f) => (
                      <tr key={f.symbol} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <div className="font-medium text-gray-900">{f.name}</div>
                          <div className="text-xs text-gray-500">{f.moneyness || ""}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1.5 flex-wrap">
                            {f.assignment_risk && (
                              <span className="text-[10px] font-semibold bg-red-50 text-red-700 border border-red-200 px-1.5 py-0.5 rounded">
                                ASSIGNMENT RISK
                              </span>
                            )}
                            {f.near_expiry && (
                              <span className="text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded">
                                ≤7 DTE
                              </span>
                            )}
                            {f.is_short && (
                              <span className="text-[10px] font-semibold bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                                SHORT
                              </span>
                            )}
                          </div>
                        </td>
                        <td className={`px-4 py-3 text-right tabular-nums ${f.dte != null && f.dte <= 7 ? "text-amber-600 font-medium" : "text-gray-600"}`}>
                          {f.dte != null ? `${f.dte}d` : "—"}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-gray-700">{f.quantity}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{fmtCurrency(f.value)}</td>
                        <td className={`px-4 py-3 text-right tabular-nums ${colorClass(f.total_return_pct)}`}>{fmtPct(f.total_return_pct)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="border border-gray-200 rounded-2xl p-5">
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`mt-2 text-2xl font-semibold tabular-nums ${color || "text-gray-900"}`}>{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-gray-200 rounded-2xl overflow-hidden mb-8">
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 text-sm font-semibold text-gray-700">{title}</div>
      {children}
    </div>
  );
}
