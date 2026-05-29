"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface IBKRStatus {
  connected: boolean;
  provider_item_id?: string | null;
  last_sync_at?: string | null;
  base_url?: string | null;
}

interface SyncResult {
  synced: number;
  skipped: number;
  options_seen?: number;
  skipped_samples?: Record<string, unknown>[];
}

function formatLastSync(iso: string | null | undefined): string {
  if (!iso) return "never";
  const date = new Date(iso);
  const diffMin = Math.round((Date.now() - date.getTime()) / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  if (diffMin < 1440) return `${Math.round(diffMin / 60)}h ago`;
  return date.toLocaleString();
}

export function IBKRConnect({
  token,
  onSyncComplete,
}: {
  token: string;
  onSyncComplete: () => void;
}) {
  const [status, setStatus] = useState<IBKRStatus | null>(null);
  const [showConnect, setShowConnect] = useState(false);
  const [baseUrl, setBaseUrl] = useState("https://localhost:5000");
  const [verifySsl, setVerifySsl] = useState(false);
  const [busy, setBusy] = useState<"connect" | "sync" | "disconnect" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<SyncResult | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!token) return;
    const res = await fetch(`${API_URL}/api/ibkr/status`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data: IBKRStatus = await res.json();
      setStatus(data);
      if (data.base_url) setBaseUrl(data.base_url);
    }
  }, [token]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || busy) return;
    setError(null);
    setBusy("connect");
    try {
      const res = await fetch(`${API_URL}/api/ibkr/connect`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ base_url: baseUrl, verify_ssl: verifySsl }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      setShowConnect(false);
      await fetchStatus();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const handleSync = async () => {
    if (!token || busy) return;
    setError(null);
    setBusy("sync");
    try {
      const res = await fetch(`${API_URL}/api/ibkr/sync`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const data: SyncResult = await res.json();
      setLastResult(data);
      await fetchStatus();
      onSyncComplete();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const handleDisconnect = async () => {
    if (!token || busy) return;
    if (!confirm("Disconnect IBKR? Your synced holdings stay until you delete the IBKR Portfolio account.")) return;
    setBusy("disconnect");
    try {
      await fetch(`${API_URL}/api/ibkr/disconnect`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      setLastResult(null);
      await fetchStatus();
    } finally {
      setBusy(null);
    }
  };

  if (!status) {
    return null; // first render before fetch
  }

  return (
    <div className="border border-gray-200 rounded-2xl p-6 mb-8">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-lg font-semibold">Interactive Brokers</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Sync live positions from your IBKR account via the self-hosted Client Portal Gateway.
          </p>
        </div>
        {status.connected ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2.5 py-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            Connected
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded-full px-2.5 py-1">
            Not connected
          </span>
        )}
      </div>

      {status.connected ? (
        <div>
          <div className="grid grid-cols-2 gap-3 text-xs text-gray-600 mb-4">
            <div>
              <div className="text-gray-400 uppercase tracking-wide mb-0.5">Account</div>
              <div className="font-mono text-gray-800">{status.provider_item_id || "—"}</div>
            </div>
            <div>
              <div className="text-gray-400 uppercase tracking-wide mb-0.5">Last sync</div>
              <div className="text-gray-800">{formatLastSync(status.last_sync_at)}</div>
            </div>
          </div>
          {lastResult && (
            <div className="text-xs text-gray-600 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 mb-3">
              <div>
                Synced <span className="font-semibold text-gray-900">{lastResult.synced}</span> positions
                {lastResult.options_seen ? `, ${lastResult.options_seen} options seen` : ""}
                {lastResult.skipped > 0 ? `, skipped ${lastResult.skipped}` : ""}.
              </div>
              {lastResult.skipped_samples && lastResult.skipped_samples.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-gray-500 hover:text-gray-700">
                    Inspect skipped rows ({lastResult.skipped_samples.length} sample{lastResult.skipped_samples.length > 1 ? "s" : ""})
                  </summary>
                  <pre className="mt-2 p-2 bg-white border border-gray-200 rounded text-[10px] overflow-x-auto leading-tight">
                    {JSON.stringify(lastResult.skipped_samples, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          )}
          <div className="flex gap-2">
            <button
              onClick={handleSync}
              disabled={busy !== null}
              className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50 transition"
            >
              {busy === "sync" ? "Syncing..." : "Sync now"}
            </button>
            <button
              onClick={handleDisconnect}
              disabled={busy !== null}
              className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-50 transition"
            >
              Disconnect
            </button>
          </div>
        </div>
      ) : showConnect ? (
        <form onSubmit={handleConnect} className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Gateway URL</label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://localhost:5000"
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
            />
            <p className="text-xs text-gray-500 mt-1">
              Where your Client Portal Gateway is running. Default is{" "}
              <code className="bg-gray-100 px-1 py-0.5 rounded">https://localhost:5000</code>.
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={verifySsl}
              onChange={(e) => setVerifySsl(e.target.checked)}
              className="rounded border-gray-300"
            />
            Verify SSL certificate (off by default — gateway uses a self-signed cert)
          </label>
          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={busy !== null}
              className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50 transition"
            >
              {busy === "connect" ? "Connecting..." : "Connect"}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowConnect(false);
                setError(null);
              }}
              className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div>
          <p className="text-sm text-gray-600 mb-3">
            Run IBKR&apos;s Client Portal Gateway locally, log in via browser, then connect here.
          </p>
          <button
            onClick={() => setShowConnect(true)}
            className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800 transition"
          >
            Connect IBKR
          </button>
        </div>
      )}

      {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
    </div>
  );
}
