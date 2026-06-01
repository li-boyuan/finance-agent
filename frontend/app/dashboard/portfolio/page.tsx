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

  // Allocation by net market value, sized by |net value| so a net-short group
  // still registers as a slice. Every group gets its own slice; palette cycles
  // if there are more groups than colors.
  const groupsByExposure = [...groups].sort(
    (a, b) => Math.abs(b.totalValue) - Math.abs(a.totalValue),
  );
  const donutData = groupsByExposure
    .filter((g) => Math.abs(g.totalValue) > 0)
    .map((g, i) => ({
      label: g.label === "Other Assets" ? "Assets" : g.label,
      value: Math.abs(g.totalValue),
      color: PALETTE[i % PALETTE.length],
    }));
  const donutTotal = donutData.reduce((s, d) => s + d.value, 0);

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-semibold">Portfolio</h1>
            <p className="text-sm text-gray-500 mt-1">
              {summary.positions_count} position{summary.positions_count === 1 ? "" : "s"} ·
              synced from IBKR · live prices via Yahoo (5-min cache)
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

            <NetWorthChart token={token} />

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
                <GroupedHoldingsTable holdings={summary.holdings} collapsible />
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

function fmtShortDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function NetWorthChart({ token }: { token: string }) {
  const [history, setHistory] = useState<{ date: string; net_worth: number }[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!token) return;
    let active = true;
    fetch(`${API_URL}/api/portfolio/history?days=365`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : { history: [] }))
      .then((d) => { if (active) setHistory(d.history || []); })
      .catch(() => {})
      .finally(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, [token]);

  if (!loaded) return null;

  if (history.length === 0) {
    return (
      <div className="border border-gray-200 rounded-2xl p-6 mb-8">
        <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-1">Net worth trend</h3>
        <p className="text-sm text-gray-500">
          Building — a snapshot is recorded each time you open this page. The trend line appears once a few days accumulate.
        </p>
      </div>
    );
  }

  const vals = history.map((h) => h.net_worth);
  const n = history.length;
  const current = vals[n - 1];
  const first = vals[0];
  const change = current - first;
  const changePct = first ? (change / Math.abs(first)) * 100 : 0;
  const up = change >= 0;

  const W = 800;
  const H = 160;
  const padY = 12;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const x = (i: number) => (n > 1 ? (i / (n - 1)) * W : W / 2);
  const yOf = (v: number) => H - padY - ((v - min) / span) * (H - 2 * padY);
  const pts = history.map((h, i) => `${x(i)},${yOf(h.net_worth)}`);
  const stroke = up ? "#10b981" : "#ef4444";
  const fill = up ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.12)";
  const areaPath = `M ${x(0)},${H} L ${pts.join(" L ")} L ${x(n - 1)},${H} Z`;

  return (
    <div className="border border-gray-200 rounded-2xl p-6 mb-8">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide">Net worth</h3>
          <div className="mt-1 text-2xl font-semibold tabular-nums text-gray-900">{fmtCurrency(current)}</div>
        </div>
        {n > 1 && (
          <div className={`text-sm tabular-nums ${colorClass(change)}`}>
            {change >= 0 ? "+" : ""}{fmtCurrency(change)} ({fmtPct(changePct)})
            <span className="text-gray-400"> · since {fmtShortDate(history[0].date)}</span>
          </div>
        )}
      </div>
      {n >= 2 ? (
        <>
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="160" preserveAspectRatio="none">
            <path d={areaPath} fill={fill} stroke="none" />
            <polyline
              points={pts.join(" ")}
              fill="none"
              stroke={stroke}
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </svg>
          <div className="flex justify-between text-xs text-gray-400 mt-2">
            <span>{fmtShortDate(history[0].date)}</span>
            <span>{fmtShortDate(history[n - 1].date)}</span>
          </div>
        </>
      ) : (
        <p className="text-sm text-gray-500">
          First snapshot recorded today — the trend line builds as more days accumulate.
        </p>
      )}
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
