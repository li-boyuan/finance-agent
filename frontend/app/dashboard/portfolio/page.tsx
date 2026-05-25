"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const PALETTE = [
  "#10b981", "#3b82f6", "#f59e0b", "#8b5cf6", "#ec4899",
  "#06b6d4", "#84cc16", "#f97316", "#a855f7", "#14b8a6",
];

interface HoldingRow {
  id: string;
  symbol: string;
  name: string;
  security_type: string;
  is_market: boolean;
  quantity: number;
  cost_basis: number;
  price: number;
  value: number;
  cost_total: number;
  total_return: number;
  total_return_pct: number;
  day_change: number;
  day_change_pct: number;
  allocation_pct: number;
  quote_available: boolean;
}

const TYPE_BADGE: Record<string, string> = {
  stock: "STK",
  etf: "ETF",
  mutual_fund: "MF",
  bond: "BND",
  crypto: "CRY",
  option: "OPT",
  real_estate: "RE",
  vehicle: "CAR",
  other: "OTH",
};

interface Summary {
  total_value: number;
  total_cost: number;
  total_return: number;
  total_return_pct: number;
  today_change: number;
  today_change_pct: number;
  positions_count: number;
  holdings: HoldingRow[];
}

function fmtCurrency(n: number) {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function fmtPct(n: number) {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function colorClass(n: number) {
  if (n > 0) return "text-emerald-600";
  if (n < 0) return "text-red-600";
  return "text-gray-500";
}

function Donut({ data }: { data: { label: string; value: number; color: string }[] }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const radius = 64;
  const stroke = 26;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <svg width="170" height="170" viewBox="0 0 170 170">
      <circle
        cx="85"
        cy="85"
        r={radius}
        fill="none"
        stroke="#f3f4f6"
        strokeWidth={stroke}
      />
      {data.map((d) => {
        const fraction = d.value / total;
        const arc = circumference * fraction;
        const el = (
          <circle
            key={d.label}
            cx="85"
            cy="85"
            r={radius}
            fill="none"
            stroke={d.color}
            strokeWidth={stroke}
            strokeDasharray={`${arc} ${circumference - arc}`}
            strokeDashoffset={-offset}
            transform="rotate(-90 85 85)"
            strokeLinecap="butt"
          />
        );
        offset += arc;
        return el;
      })}
    </svg>
  );
}

export default function PortfolioPage() {
  const router = useRouter();
  const supabase = createClient();
  const [token, setToken] = useState<string>("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        if (!session) {
          router.push("/login");
          return;
        }
        setToken(session.access_token);
      },
    );
    return () => subscription.unsubscribe();
  }, [router, supabase]);

  const fetchSummary = useCallback(
    async (showSpinner = false) => {
      if (!token) return;
      if (showSpinner) setRefreshing(true);
      setError(null);
      try {
        const res = await fetch(`${API_URL}/api/portfolio/summary`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: Summary = await res.json();
        setSummary(data);
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
    if (token) fetchSummary();
  }, [token, fetchSummary]);

  if (loading && !summary) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400">
        Loading portfolio...
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="h-full flex items-center justify-center text-red-600">
        {error || "Could not load portfolio."}
      </div>
    );
  }

  const empty = summary.positions_count === 0;

  // Build donut data — top 9 holdings, group rest as "Other".
  const sorted = [...summary.holdings].sort((a, b) => b.value - a.value);
  const top = sorted.slice(0, 9);
  const rest = sorted.slice(9);
  const restValue = rest.reduce((s, h) => s + h.value, 0);
  const donutData = [
    ...top.map((h, i) => ({ label: h.symbol, value: h.value, color: PALETTE[i] })),
    ...(restValue > 0
      ? [{ label: "Other", value: restValue, color: "#9ca3af" }]
      : []),
  ];

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-semibold">Portfolio</h1>
            <p className="text-sm text-gray-500 mt-1">
              {summary.positions_count} position{summary.positions_count === 1 ? "" : "s"} ·
              Prices via Yahoo Finance, cached 5 min
            </p>
          </div>
          <button
            onClick={() => fetchSummary(true)}
            disabled={refreshing}
            className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition"
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        {empty ? (
          <div className="border border-gray-200 rounded-2xl p-12 text-center">
            <h2 className="text-lg font-semibold mb-2">No holdings yet</h2>
            <p className="text-gray-500 mb-6">
              Add a few holdings to see your portfolio overview, allocation, and performance.
            </p>
            <Link
              href="/dashboard/holdings"
              className="inline-block bg-gray-900 text-white px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-gray-800 transition"
            >
              Add holdings →
            </Link>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              <StatCard label="Total Value" value={fmtCurrency(summary.total_value)} />
              <StatCard
                label="Today"
                value={fmtCurrency(summary.today_change)}
                sub={fmtPct(summary.today_change_pct)}
                color={colorClass(summary.today_change)}
              />
              <StatCard
                label="Total Return"
                value={fmtCurrency(summary.total_return)}
                sub={fmtPct(summary.total_return_pct)}
                color={colorClass(summary.total_return)}
              />
              <StatCard
                label="Positions"
                value={summary.positions_count.toString()}
              />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
              <div className="lg:col-span-1 border border-gray-200 rounded-2xl p-6">
                <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-4">
                  Allocation
                </h3>
                <div className="flex flex-col items-center">
                  <Donut data={donutData} />
                  <div className="mt-6 w-full space-y-1.5">
                    {donutData.map((d) => (
                      <div key={d.label} className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <span
                            className="w-2.5 h-2.5 rounded-sm"
                            style={{ backgroundColor: d.color }}
                          />
                          <span className="text-gray-700">{d.label}</span>
                        </div>
                        <span className="text-gray-500 tabular-nums">
                          {((d.value / summary.total_value) * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="lg:col-span-2 border border-gray-200 rounded-2xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                      <th className="px-4 py-3">Symbol</th>
                      <th className="px-4 py-3 text-right">Qty</th>
                      <th className="px-4 py-3 text-right">Price</th>
                      <th className="px-4 py-3 text-right">Day</th>
                      <th className="px-4 py-3 text-right">Value</th>
                      <th className="px-4 py-3 text-right">Return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((h) => (
                      <tr
                        key={h.id}
                        className="border-b border-gray-100 last:border-0 hover:bg-gray-50"
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-gray-900">
                              {h.is_market ? h.symbol : h.name}
                            </span>
                            <span className="text-[10px] font-semibold bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                              {TYPE_BADGE[h.security_type] || h.security_type.slice(0, 3).toUpperCase()}
                            </span>
                          </div>
                          {h.is_market && h.name && (
                            <div className="text-xs text-gray-500 truncate max-w-[220px]">
                              {h.name}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                          {h.is_market ? h.quantity : "—"}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {h.is_market
                            ? h.quote_available ? fmtCurrency(h.price) : "—"
                            : "—"}
                        </td>
                        <td className={`px-4 py-3 text-right tabular-nums ${h.is_market ? colorClass(h.day_change) : "text-gray-400"}`}>
                          {h.is_market
                            ? (h.quote_available ? fmtPct(h.day_change_pct) : "—")
                            : "—"}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {fmtCurrency(h.value)}
                        </td>
                        <td className={`px-4 py-3 text-right tabular-nums ${colorClass(h.total_return)}`}>
                          {fmtPct(h.total_return_pct)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex justify-center">
              <Link
                href="/dashboard/holdings"
                className="text-sm text-gray-600 hover:text-gray-900 transition"
              >
                Manage holdings →
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="border border-gray-200 rounded-2xl p-5">
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold text-gray-900 tabular-nums">
        {value}
      </div>
      {sub && (
        <div className={`text-sm mt-1 tabular-nums ${color || "text-gray-500"}`}>
          {sub}
        </div>
      )}
    </div>
  );
}
