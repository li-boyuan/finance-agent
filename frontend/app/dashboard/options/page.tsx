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
  theta_day: number | null;
  net_vega: number;
  scenario_pl: number | null;
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
  theta_day: number | null;
  assignment_risk: boolean;
  near_expiry: boolean;
  total_return_pct: number;
}

interface Indicator {
  key: string;
  label: string;
  value: number | null;
  display: string;
  rating: string | null;
}

interface Margin {
  net_liquidation: number;
  excess_liquidity: number | null;
  buying_power: number | null;
  maint_margin: number | null;
  gross_position_value: number | null;
  margin_util: number | null;
  leverage: number | null;
  as_of: string | null;
}

interface Scenario {
  move_pct: number;
  iv_points: number;
  pl: number;
  pl_pct_nlv: number | null;
  partial: boolean;
}

interface Analytics {
  as_of: string;
  has_greeks: boolean;
  totals: {
    option_value: number;
    leg_count: number;
    near_expiry: number;
    assignment_risk: number;
    net_delta_dollars: number;
    theta_day: number;
    net_vega: number;
    scenario_pl: number;
  };
  underlyings: UnderlyingRow[];
  expirations: Expiration[];
  flags: FlagLeg[];
  margin: Margin | null;
  scenario: Scenario;
  indicators: Indicator[];
  overall_rating: string | null;
}

const RATING_STYLE: Record<string, { text: string; bg: string; border: string; label: string }> = {
  conservative: { text: "text-emerald-700", bg: "bg-emerald-50", border: "border-emerald-200", label: "Conservative" },
  moderate: { text: "text-amber-700", bg: "bg-amber-50", border: "border-amber-200", label: "Moderate" },
  aggressive: { text: "text-orange-700", bg: "bg-orange-50", border: "border-orange-200", label: "Aggressive" },
  high: { text: "text-red-700", bg: "bg-red-50", border: "border-red-200", label: "High risk" },
};

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

            <RiskScorecard
              overall={data.overall_rating}
              indicators={data.indicators}
              scenario={data.scenario}
            />

            {data.margin ? (
              <MarginPanel margin={data.margin} />
            ) : (
              <div className="mb-8 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-600">
                Apply migration <code className="font-mono">007_account_balances.sql</code> and re-sync IBKR to
                see margin, buying power, and the account-relative risk ratings (utilization, leverage,
                concentration, shock loss).
              </div>
            )}

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
              <StatCard label="Net Δ$ exposure" value={fmtCurrency(data.totals.net_delta_dollars)} />
              <StatCard
                label="Theta / day"
                value={fmtCurrency(data.totals.theta_day)}
                color={colorClass(data.totals.theta_day)}
              />
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
                    <th className="px-4 py-3 text-right">Theta/day</th>
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
                      <td className={`px-4 py-3 text-right tabular-nums ${u.theta_day != null ? colorClass(u.theta_day) : ""}`}>
                        {u.theta_day != null ? fmtCurrency(u.theta_day) : "—"}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">{fmtCurrency(u.option_value)}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-500">{u.leg_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.underlyings.some((u) => u.delta_partial) && (
                <div className="px-4 py-2 text-xs text-gray-400">
                  * net delta is partial — some legs are missing greeks (IBKR doesn’t quote adjusted / illiquid contracts).
                </div>
              )}
            </Section>

            <Section title="Expirations timeline">
              <ExpirationsTimeline expirations={data.expirations} />
            </Section>

            {data.flags.length > 0 && (
              <Section title="Risk flags">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                      <th className="px-4 py-3">Contract</th>
                      <th className="px-4 py-3">Flags</th>
                      <th className="px-4 py-3 text-right">DTE</th>
                      <th className="px-4 py-3 text-right">Theta/day</th>
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
                        <td className={`px-4 py-3 text-right tabular-nums ${f.theta_day != null ? colorClass(f.theta_day) : ""}`}>
                          {f.theta_day != null ? fmtCurrency(f.theta_day) : "—"}
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

function RatingBadge({ rating, big }: { rating: string; big?: boolean }) {
  const s = RATING_STYLE[rating] || RATING_STYLE.moderate;
  return (
    <span className={`inline-block font-semibold rounded border ${s.bg} ${s.text} ${s.border} ${big ? "text-sm px-2.5 py-1" : "text-[10px] px-1.5 py-0.5"}`}>
      {s.label}
    </span>
  );
}

function RiskScorecard({
  overall,
  indicators,
  scenario,
}: {
  overall: string | null;
  indicators: Indicator[];
  scenario: Scenario;
}) {
  return (
    <div className="border border-gray-200 rounded-2xl p-5 mb-8">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide">Aggressiveness</h3>
        {overall ? (
          <RatingBadge rating={overall} big />
        ) : (
          <span className="text-xs text-gray-400">sync IBKR for margin-based rating</span>
        )}
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {indicators.map((i) => (
          <div
            key={i.key}
            className={`rounded-xl border p-3 ${i.rating ? RATING_STYLE[i.rating].border : "border-gray-200"}`}
          >
            <div className="text-xs text-gray-500">{i.label}</div>
            <div className="mt-1 text-xl font-semibold tabular-nums text-gray-900">{i.display}</div>
            <div className="mt-1.5">
              {i.rating ? (
                <RatingBadge rating={i.rating} />
              ) : (
                <span className="text-[10px] text-gray-400">needs margin sync</span>
              )}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 text-sm text-gray-600">
        Risk shock ({(scenario.move_pct * 100).toFixed(0)}% &amp; +{scenario.iv_points} IV pts):{" "}
        <span className={`font-semibold ${colorClass(scenario.pl)}`}>{fmtCurrency(scenario.pl)}</span>
        {scenario.pl_pct_nlv != null && (
          <span className="text-gray-500"> ({(scenario.pl_pct_nlv * 100).toFixed(0)}% of NLV)</span>
        )}
        {scenario.partial && (
          <span className="text-xs text-amber-600"> · partial — some legs missing greeks</span>
        )}
      </div>
    </div>
  );
}

function MarginPanel({ margin }: { margin: Margin }) {
  const util = margin.margin_util;
  const utilColor = util == null ? "bg-gray-300" : util < 0.5 ? "bg-emerald-400" : util < 0.75 ? "bg-amber-400" : "bg-red-400";
  const cells: { label: string; value: string }[] = [
    { label: "Net liquidation", value: fmtCurrency(margin.net_liquidation) },
    { label: "Excess liquidity", value: margin.excess_liquidity != null ? fmtCurrency(margin.excess_liquidity) : "—" },
    { label: "Buying power", value: margin.buying_power != null ? fmtCurrency(margin.buying_power) : "—" },
    { label: "Maint margin", value: margin.maint_margin != null ? fmtCurrency(margin.maint_margin) : "—" },
  ];
  return (
    <Section title="Margin & buying power">
      <div className="p-5">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
          {cells.map((c) => (
            <div key={c.label}>
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{c.label}</div>
              <div className="mt-1 text-lg font-semibold tabular-nums text-gray-900">{c.value}</div>
            </div>
          ))}
        </div>
        {util != null && (
          <div>
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>Margin utilization (maint ÷ NLV)</span>
              <span className="tabular-nums">{(util * 100).toFixed(0)}%</span>
            </div>
            <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
              <div className={`h-full rounded-full ${utilColor}`} style={{ width: `${Math.min(util * 100, 100)}%` }} />
            </div>
          </div>
        )}
      </div>
    </Section>
  );
}

function ExpirationsTimeline({ expirations }: { expirations: Expiration[] }) {
  const maxAbs = Math.max(1, ...expirations.map((e) => Math.abs(e.net_value)));
  return (
    <div className="p-5">
      <div className="flex items-center gap-3 mb-5 text-[11px] text-gray-400">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" /> ≤7d</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500" /> ≤30d</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> later</span>
        <span className="ml-auto">bar ∝ |net value|</span>
      </div>
      <div className="relative">
        {/* the timeline spine */}
        <div className="absolute left-2 top-1 bottom-1 w-px bg-gray-200" />
        <div className="space-y-5">
          {expirations.map((e) => {
            const near = e.dte != null && e.dte <= 7;
            const soon = e.dte != null && e.dte <= 30;
            const pct = Math.max(2, (Math.abs(e.net_value) / maxAbs) * 100);
            const dot = near ? "bg-red-500" : soon ? "bg-amber-500" : "bg-emerald-500";
            return (
              <div key={e.expiry} className="relative pl-8">
                <div className={`absolute left-[3px] top-1.5 w-3 h-3 rounded-full border-2 border-white ${dot}`} />
                <div className="flex items-baseline justify-between gap-3">
                  <div className="flex items-baseline gap-2">
                    <span className="font-semibold text-gray-900">{fmtExpiry(e.expiry)}</span>
                    <span className={`text-xs ${near ? "text-red-600 font-medium" : soon ? "text-amber-600" : "text-gray-400"}`}>
                      {e.dte != null ? `${e.dte}d` : ""}
                    </span>
                  </div>
                  <span className={`text-sm tabular-nums font-medium ${colorClass(e.net_value)}`}>
                    {fmtCurrency(e.net_value)}
                  </span>
                </div>
                <div className="mt-2 h-2 rounded-full bg-gray-100 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${e.net_value >= 0 ? "bg-emerald-400" : "bg-rose-400"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs text-gray-500 mr-1">
                    {e.leg_count} leg{e.leg_count === 1 ? "" : "s"}
                  </span>
                  {e.underlyings.map((u) => (
                    <span key={u} className="text-[10px] font-semibold bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                      {u}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
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
