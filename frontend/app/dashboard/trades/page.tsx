"use client";

import { useEffect, useState, useCallback } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Stats {
  total_trades: number;
  closed_trades: number;
  open_trades: number;
  win_rate: number;
  total_pnl: number;
  today_pnl: number;
}

interface Trade {
  id: string;
  symbol: string;
  side: string;
  status: string;
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  entry_time: string;
  pnl: number | null;
  pnl_percent: number | null;
  setup_type: string | null;
  tags: string[];
}

interface IBKRStatus {
  connected: boolean;
  account_id?: string;
  status?: string;
  last_sync_at?: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const supabase = createClient();
  const [user, setUser] = useState<{ email?: string } | null>(null);
  const [token, setToken] = useState<string>("");
  const [stats, setStats] = useState<Stats | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [ibkrStatus, setIbkrStatus] = useState<IBKRStatus>({ connected: false });
  const [syncing, setSyncing] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        if (!session) {
          router.push("/login");
          return;
        }
        setUser(session.user);
        setToken(session.access_token);
      },
    );
    return () => subscription.unsubscribe();
  }, []);

  const fetchData = useCallback(async () => {
    if (!token) return;
    const headers = {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    };

    const [statsRes, tradesRes, ibkrRes] = await Promise.all([
      fetch(`${API_URL}/api/trades/stats`, { headers }),
      fetch(`${API_URL}/api/trades/?limit=20`, { headers }),
      fetch(`${API_URL}/api/ibkr/status`, { headers }),
    ]);

    if (statsRes.ok) setStats(await statsRes.json());
    if (tradesRes.ok) {
      const data = await tradesRes.json();
      setTrades(data.trades || []);
    }
    if (ibkrRes.ok) setIbkrStatus(await ibkrRes.json());
    setLoading(false);
  }, [token]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleSync() {
    setSyncing(true);
    const res = await fetch(`${API_URL}/api/ibkr/sync`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      await fetchData();
    }
    setSyncing(false);
  }

  async function handleConnectIBKR() {
    const res = await fetch(`${API_URL}/api/ibkr/auth-url`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const { url } = await res.json();
      window.location.href = url;
    }
  }

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.push("/login");
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-gray-400">Loading...</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-8">
      <header className="flex items-center justify-between border-b border-gray-800 pb-4">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-400">{user?.email}</span>
          <button
            onClick={handleSignOut}
            className="text-sm text-gray-500 hover:text-gray-300 transition"
          >
            Sign Out
          </button>
        </div>
      </header>

      <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Today P&L"
          value={stats ? formatPnl(stats.today_pnl) : "--"}
          color={stats && stats.today_pnl !== 0 ? (stats.today_pnl > 0 ? "green" : "red") : undefined}
        />
        <StatCard
          label="Win Rate"
          value={stats ? `${stats.win_rate}%` : "--"}
        />
        <StatCard
          label="Total Trades"
          value={stats ? String(stats.total_trades) : "0"}
        />
        <StatCard
          label="IBKR Status"
          value={ibkrStatus.connected ? "Connected" : "Not Connected"}
          action={
            ibkrStatus.connected ? (
              <button
                onClick={handleSync}
                disabled={syncing}
                className="mt-2 text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50"
              >
                {syncing ? "Syncing..." : "Sync Now"}
              </button>
            ) : (
              <button
                onClick={handleConnectIBKR}
                className="mt-2 text-xs text-blue-400 hover:text-blue-300"
              >
                Connect
              </button>
            )
          }
        />
      </div>

      {stats && stats.total_pnl !== 0 && (
        <div className="mt-6 rounded-lg border border-gray-800 p-5">
          <p className="text-sm text-gray-400">Total P&L</p>
          <p className={`mt-1 text-3xl font-bold ${stats.total_pnl > 0 ? "text-green-400" : "text-red-400"}`}>
            {formatPnl(stats.total_pnl)}
          </p>
          <p className="mt-1 text-sm text-gray-500">
            {stats.closed_trades} closed · {stats.open_trades} open
          </p>
        </div>
      )}

      <section className="mt-10">
        <h2 className="text-lg font-semibold mb-4">Recent Trades</h2>
        {trades.length === 0 ? (
          <div className="rounded-lg border border-gray-800 p-8 text-center text-gray-500">
            {ibkrStatus.connected
              ? 'Click "Sync Now" to import your trades from IBKR.'
              : "Connect your IBKR account to start importing trades."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-gray-400">
                  <th className="pb-3 pr-4">Symbol</th>
                  <th className="pb-3 pr-4">Side</th>
                  <th className="pb-3 pr-4">Entry</th>
                  <th className="pb-3 pr-4">Exit</th>
                  <th className="pb-3 pr-4">Qty</th>
                  <th className="pb-3 pr-4">P&L</th>
                  <th className="pb-3 pr-4">Status</th>
                  <th className="pb-3">Time</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => (
                  <tr key={trade.id} className="border-b border-gray-800/50 hover:bg-gray-900/50">
                    <td className="py-3 pr-4 font-medium">{trade.symbol}</td>
                    <td className="py-3 pr-4">
                      <span className={trade.side === "long" ? "text-green-400" : "text-red-400"}>
                        {trade.side.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3 pr-4">${trade.entry_price.toFixed(2)}</td>
                    <td className="py-3 pr-4">
                      {trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : "—"}
                    </td>
                    <td className="py-3 pr-4">{trade.quantity}</td>
                    <td className="py-3 pr-4">
                      {trade.pnl !== null ? (
                        <span className={trade.pnl > 0 ? "text-green-400" : "text-red-400"}>
                          {formatPnl(trade.pnl)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      <span
                        className={`rounded px-2 py-0.5 text-xs ${
                          trade.status === "open"
                            ? "bg-blue-900/50 text-blue-300"
                            : "bg-gray-800 text-gray-400"
                        }`}
                      >
                        {trade.status}
                      </span>
                    </td>
                    <td className="py-3 text-gray-400">
                      {new Date(trade.entry_time).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

function StatCard({
  label,
  value,
  color,
  action,
}: {
  label: string;
  value: string;
  color?: "green" | "red";
  action?: React.ReactNode;
}) {
  const colorClass =
    color === "green"
      ? "text-green-400"
      : color === "red"
        ? "text-red-400"
        : "";

  return (
    <div className="rounded-lg border border-gray-800 p-5">
      <p className="text-sm text-gray-400">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${colorClass}`}>{value}</p>
      {action}
    </div>
  );
}

function formatPnl(value: number): string {
  const prefix = value >= 0 ? "+$" : "-$";
  return `${prefix}${Math.abs(value).toFixed(2)}`;
}
