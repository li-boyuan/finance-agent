"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { GroupedHoldingsTable } from "@/components/portfolio/GroupedHoldingsTable";
import {
  PortfolioSummary,
  buildGroups,
  colorClass,
  fmtCurrency,
  fmtPct,
} from "@/components/portfolio/grouping";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const PALETTE = [
  "#10b981", "#3b82f6", "#f59e0b", "#8b5cf6", "#ec4899",
  "#06b6d4", "#84cc16", "#f97316", "#a855f7", "#14b8a6",
];

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
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
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
        const data: PortfolioSummary = await res.json();
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

  // Group holdings by underlying ticker so stock + options for the same name appear together.
  const groups = buildGroups(summary.holdings);

  // Donut sized by abs(value) so short positions still register, top 9 groups + rest.
  const groupsByExposure = [...groups].sort(
    (a, b) => Math.abs(b.totalValue) - Math.abs(a.totalValue),
  );
  const topGroups = groupsByExposure.slice(0, 9);
  const restGroups = groupsByExposure.slice(9);
  const restValue = restGroups.reduce((s, g) => s + Math.abs(g.totalValue), 0);
  const donutData = [
    ...topGroups.map((g, i) => ({
      label: g.label === "Other Assets" ? "Assets" : g.label,
      value: Math.abs(g.totalValue),
      color: PALETTE[i],
    })),
    ...(restValue > 0
      ? [{ label: "Other", value: restValue, color: "#9ca3af" }]
      : []),
  ];
  const donutTotal = donutData.reduce((s, d) => s + d.value, 0);

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
                          {donutTotal ? ((d.value / donutTotal) * 100).toFixed(1) : "0.0"}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="lg:col-span-2 border border-gray-200 rounded-2xl overflow-hidden">
                <GroupedHoldingsTable holdings={summary.holdings} />
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
