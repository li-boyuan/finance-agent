"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const PLAID_LINK_SRC = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";

// Load Plaid Link from the CDN on demand (avoids an npm dependency).
function loadPlaid(): Promise<any> {
  return new Promise((resolve, reject) => {
    const w = window as unknown as { Plaid?: unknown };
    if (w.Plaid) return resolve(w.Plaid);
    const s = document.createElement("script");
    s.src = PLAID_LINK_SRC;
    s.async = true;
    s.onload = () => resolve((window as unknown as { Plaid: unknown }).Plaid);
    s.onerror = () => reject(new Error("Failed to load Plaid Link"));
    document.body.appendChild(s);
  });
}

interface PlaidStatus {
  connected: boolean;
  configured: boolean;
  connection_id?: string;
  institution_name?: string | null;
  last_sync_at?: string | null;
}

export function PlaidConnect({
  token,
  onSyncComplete,
}: {
  token: string;
  onSyncComplete: () => void;
}) {
  const [status, setStatus] = useState<PlaidStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!token) return;
    const res = await fetch(`${API_URL}/api/plaid/status`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setStatus(await res.json());
  }, [token]);

  useEffect(() => {
    if (token) fetchStatus();
  }, [token, fetchStatus]);

  const connect = async () => {
    if (!token || busy) return;
    setError(null);
    setBusy(true);
    try {
      const Plaid = await loadPlaid();
      const ltRes = await fetch(`${API_URL}/api/plaid/link-token`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!ltRes.ok) {
        const b = await ltRes.json().catch(() => ({}));
        throw new Error(b.detail || `HTTP ${ltRes.status}`);
      }
      const { link_token } = await ltRes.json();
      const handler = (Plaid as { create: (o: unknown) => { open: () => void } }).create({
        token: link_token,
        onSuccess: async (public_token: string, metadata: { institution?: { name?: string } }) => {
          try {
            const exRes = await fetch(`${API_URL}/api/plaid/exchange`, {
              method: "POST",
              headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
              body: JSON.stringify({ public_token, institution_name: metadata?.institution?.name }),
            });
            if (!exRes.ok) {
              const b = await exRes.json().catch(() => ({}));
              throw new Error(b.detail || `HTTP ${exRes.status}`);
            }
            await fetchStatus();
            onSyncComplete();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        },
        onExit: (err: { display_message?: string; error_message?: string } | null) => {
          setBusy(false);
          if (err) setError(err.display_message || err.error_message || "Link cancelled");
        },
      });
      handler.open();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  const sync = async () => {
    if (!token || busy) return;
    setError(null);
    setBusy(true);
    try {
      const res = await fetch(`${API_URL}/api/plaid/sync`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        throw new Error(b.detail || `HTTP ${res.status}`);
      }
      await fetchStatus();
      onSyncComplete();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!token || !status?.connection_id) return;
    if (!confirm("Disconnect Plaid? Already-synced holdings are kept.")) return;
    setBusy(true);
    setError(null);
    try {
      await fetch(`${API_URL}/api/plaid/disconnect/${status.connection_id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      await fetchStatus();
    } finally {
      setBusy(false);
    }
  };

  const notConfigured = status !== null && !status.configured && !status.connected;
  const btn = "px-4 py-2 rounded-lg text-sm font-medium transition disabled:opacity-50";

  return (
    <div className="border border-gray-200 rounded-2xl p-6 mb-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Fidelity &amp; banks (Plaid)</h2>
          <p className="text-sm text-gray-500 mt-1">
            {status?.connected
              ? `Connected${status.institution_name ? `: ${status.institution_name}` : ""}${
                  status.last_sync_at ? ` · last sync ${new Date(status.last_sync_at).toLocaleString()}` : ""
                }`
              : notConfigured
                ? "Plaid not configured — set PLAID_CLIENT_ID / PLAID_SECRET in backend/.env."
                : "Link a Fidelity account (IRA, Roth, 529, brokerage) to auto-import holdings."}
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          {status?.connected ? (
            <>
              <button onClick={sync} disabled={busy} className={`${btn} bg-gray-900 text-white hover:bg-gray-800`}>
                {busy ? "Syncing…" : "Sync"}
              </button>
              <button onClick={disconnect} disabled={busy} className={`${btn} border border-gray-300 text-gray-700 hover:bg-gray-50`}>
                Disconnect
              </button>
            </>
          ) : (
            <button
              onClick={connect}
              disabled={busy || notConfigured}
              className={`${btn} bg-gray-900 text-white hover:bg-gray-800`}
            >
              {busy ? "Connecting…" : "Connect Plaid"}
            </button>
          )}
        </div>
      </div>
      {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
    </div>
  );
}
