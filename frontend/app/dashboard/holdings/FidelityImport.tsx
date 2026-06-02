"use client";

import { useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface MatchedAccount {
  account: string;
  account_number: string;
  holdings: number;
  value: number;
}
interface SkippedAccount extends MatchedAccount {
  reason: string;
}
interface ImportResult {
  committed: boolean;
  as_of: string;
  total_imported: number;
  matched: MatchedAccount[];
  skipped: SkippedAccount[];
}

const fmt = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD" });

// Fidelity only shares balances via Plaid, so per-position detail comes from a
// CSV export (Fidelity.com → Positions → Download). Preview first, then confirm —
// confirming full-replaces the matched accounts' holdings.
export function FidelityImport({
  token,
  onSyncComplete,
}: {
  token: string;
  onSyncComplete: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const send = async (commit: boolean): Promise<ImportResult> => {
    const csv = await file!.text();
    const res = await fetch(`${API_URL}/api/fidelity/import`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ csv, commit }),
    });
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      throw new Error(b.detail || `HTTP ${res.status}`);
    }
    return res.json();
  };

  const doPreview = async () => {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      setPreview(await send(false));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const doConfirm = async () => {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await send(true);
      setPreview(null);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      setDone(`Imported ${r.total_imported} positions across ${r.matched.length} accounts.`);
      onSyncComplete();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onPick = (f: File | null) => {
    setFile(f);
    setPreview(null);
    setDone(null);
    setError(null);
  };

  const btn = "px-4 py-2 rounded-lg text-sm font-medium transition disabled:opacity-50";

  return (
    <div className="border border-gray-200 rounded-2xl p-6 mb-8">
      <h2 className="text-lg font-semibold">Import Fidelity positions (CSV)</h2>
      <p className="text-sm text-gray-500 mt-1">
        Fidelity only shares balances via Plaid. Export{" "}
        <span className="font-medium">Positions → Download</span> from Fidelity.com and
        import it here for per-position detail. Stocks &amp; ETFs then price live;
        re-import after you trade. (Re-running Plaid Sync reverts Fidelity to balances.)
      </p>

      <div className="flex flex-wrap items-center gap-2 mt-4">
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
          className="text-sm text-gray-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200"
        />
        {file && !preview && (
          <button onClick={doPreview} disabled={busy} className={`${btn} bg-gray-900 text-white hover:bg-gray-800`}>
            {busy ? "Reading…" : "Preview import"}
          </button>
        )}
        {preview && (
          <>
            <button onClick={doConfirm} disabled={busy} className={`${btn} bg-emerald-600 text-white hover:bg-emerald-700`}>
              {busy ? "Importing…" : "Confirm import"}
            </button>
            <button onClick={() => setPreview(null)} disabled={busy} className={`${btn} border border-gray-300 text-gray-700 hover:bg-gray-50`}>
              Cancel
            </button>
          </>
        )}
      </div>

      {preview && (
        <div className="mt-4 text-sm">
          <p className="text-gray-500 mb-3">
            Preview — nothing saved yet. Confirm to replace these accounts&apos; holdings.
          </p>
          {preview.matched.length > 0 && (
            <div className="mb-3">
              <div className="font-medium text-gray-700 mb-1">
                Will import — {preview.total_imported} positions
              </div>
              <ul className="space-y-0.5">
                {preview.matched.map((m) => (
                  <li key={m.account_number} className="flex justify-between text-gray-600">
                    <span>
                      {m.account} · {m.holdings} positions
                    </span>
                    <span className="tabular-nums">{fmt(m.value)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {preview.skipped.length > 0 && (
            <div>
              <div className="font-medium text-gray-700 mb-1">Skipped</div>
              <ul className="space-y-1.5">
                {preview.skipped.map((s) => (
                  <li key={s.account_number}>
                    <span className="flex justify-between text-gray-600">
                      <span>{s.account}</span>
                      <span className="tabular-nums">{fmt(s.value)}</span>
                    </span>
                    <span className="block text-xs text-amber-700">{s.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {done && <p className="text-sm text-emerald-700 mt-3">{done}</p>}
      {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
    </div>
  );
}
