"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { IBKRConnect } from "./IBKRConnect";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type FormKind = "market" | "option" | "asset";

const ASSET_TYPES: { value: string; label: string; kind: FormKind }[] = [
  { value: "stock", label: "Stock", kind: "market" },
  { value: "etf", label: "ETF", kind: "market" },
  { value: "mutual_fund", label: "Mutual Fund", kind: "market" },
  { value: "crypto", label: "Crypto", kind: "market" },
  { value: "option", label: "Option", kind: "option" },
  { value: "real_estate", label: "Real Estate", kind: "asset" },
  { value: "vehicle", label: "Vehicle", kind: "asset" },
  { value: "other", label: "Other Asset", kind: "asset" },
];

const TYPE_LABEL: Record<string, string> = Object.fromEntries(
  ASSET_TYPES.map((t) => [t.value, t.label]),
);

interface Holding {
  id: string;
  symbol: string;
  name: string | null;
  security_type: string;
  quantity: number;
  cost_basis: number;
  current_price: number | null;
  current_value: number | null;
  as_of: string;
}

export default function HoldingsPage() {
  const router = useRouter();
  const supabase = createClient();
  const [token, setToken] = useState<string>("");
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [securityType, setSecurityType] = useState("stock");
  const [symbol, setSymbol] = useState("");
  const [name, setName] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [costBasis, setCostBasis] = useState("");
  const [currentValue, setCurrentValue] = useState("");
  // Option-specific fields
  const [optUnderlying, setOptUnderlying] = useState("");
  const [optExpiry, setOptExpiry] = useState("");
  const [optStrike, setOptStrike] = useState("");
  const [optType, setOptType] = useState<"C" | "P">("C");
  const [submitting, setSubmitting] = useState(false);

  const selectedType = ASSET_TYPES.find((t) => t.value === securityType);
  const formKind: FormKind = selectedType?.kind ?? "market";

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

  const fetchHoldings = useCallback(async () => {
    if (!token) return;
    const res = await fetch(`${API_URL}/api/holdings/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data = await res.json();
      setHoldings(data.holdings || []);
    }
    setLoading(false);
  }, [token]);

  useEffect(() => {
    if (token) fetchHoldings();
  }, [token, fetchHoldings]);

  const resetForm = () => {
    setSymbol("");
    setName("");
    setQuantity(formKind === "asset" ? "1" : "");
    setCostBasis("");
    setCurrentValue("");
    setOptUnderlying("");
    setOptExpiry("");
    setOptStrike("");
    setOptType("C");
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        security_type: securityType,
        quantity: parseFloat(quantity),
        cost_basis: parseFloat(costBasis),
      };
      if (formKind === "market") {
        body.symbol = symbol.trim();
      } else if (formKind === "option") {
        body.underlying = optUnderlying.trim().toUpperCase();
        body.expiry = optExpiry;
        body.strike = parseFloat(optStrike);
        body.option_type = optType;
      } else {
        body.name = name.trim();
        body.current_value = parseFloat(currentValue);
      }

      const res = await fetch(`${API_URL}/api/holdings/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || `HTTP ${res.status}`);
      }
      resetForm();
      await fetchHoldings();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!token) return;
    if (!confirm("Delete this holding?")) return;
    await fetch(`${API_URL}/api/holdings/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    await fetchHoldings();
  };

  // Group holdings: market (stocks/ETFs/crypto), options, other assets
  const kindOf = (st: string): FormKind =>
    ASSET_TYPES.find((t) => t.value === st)?.kind ?? "market";
  const market = holdings.filter((h) => kindOf(h.security_type) === "market");
  const options = holdings.filter((h) => kindOf(h.security_type) === "option");
  const assets = holdings.filter((h) => kindOf(h.security_type) === "asset");

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-semibold mb-1">Holdings</h1>
        <p className="text-sm text-gray-500 mb-8">
          Add stocks, crypto, real estate, vehicles, or anything else you want in your net worth.
        </p>

        <IBKRConnect token={token} onSyncComplete={fetchHoldings} />

        <div className="border border-gray-200 rounded-2xl p-6 mb-8">
          <h2 className="text-lg font-semibold mb-4">Add a holding manually</h2>
          <form onSubmit={handleAdd} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Type</label>
              <select
                value={securityType}
                onChange={(e) => {
                  setSecurityType(e.target.value);
                  // Reset to sensible defaults when switching type kind
                  const newType = ASSET_TYPES.find((t) => t.value === e.target.value);
                  if (newType && newType.kind !== "market") setQuantity("1");
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
              >
                {ASSET_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            {formKind === "market" ? (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Symbol</label>
                  <input
                    type="text"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                    placeholder="AAPL"
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm uppercase focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Quantity</label>
                  <input
                    type="number"
                    step="0.0001"
                    min="0"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    placeholder="100"
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Cost ($/share)</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={costBasis}
                    onChange={(e) => setCostBasis(e.target.value)}
                    placeholder="180.50"
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                  />
                </div>
              </div>
            ) : formKind === "option" ? (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Underlying</label>
                    <input
                      type="text"
                      value={optUnderlying}
                      onChange={(e) => setOptUnderlying(e.target.value.toUpperCase())}
                      placeholder="AAPL"
                      required
                      maxLength={6}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm uppercase focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Expiry</label>
                    <input
                      type="date"
                      value={optExpiry}
                      onChange={(e) => setOptExpiry(e.target.value)}
                      required
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Strike</label>
                    <input
                      type="number"
                      step="0.5"
                      min="0"
                      value={optStrike}
                      onChange={(e) => setOptStrike(e.target.value)}
                      placeholder="200"
                      required
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Type</label>
                    <select
                      value={optType}
                      onChange={(e) => setOptType(e.target.value as "C" | "P")}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                    >
                      <option value="C">Call</option>
                      <option value="P">Put</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Contracts</label>
                    <input
                      type="number"
                      step="1"
                      min="0"
                      value={quantity}
                      onChange={(e) => setQuantity(e.target.value)}
                      placeholder="2"
                      required
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                      Premium ($/share)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={costBasis}
                      onChange={(e) => setCostBasis(e.target.value)}
                      placeholder="5.30"
                      required
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                    />
                  </div>
                </div>
                <p className="text-xs text-gray-500">
                  Premium is per share — each contract is 100 shares.
                  {optStrike && quantity && costBasis ? (
                    <span className="block mt-1">
                      Total cost: <span className="font-medium text-gray-700">
                        ${(parseFloat(quantity) * parseFloat(costBasis) * 100).toLocaleString()}
                      </span>
                    </span>
                  ) : null}
                </p>
              </>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Name</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={
                      securityType === "real_estate"
                        ? "Primary Residence"
                        : securityType === "vehicle"
                          ? "2019 Honda Civic"
                          : "Asset name"
                    }
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Purchase price</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={costBasis}
                    onChange={(e) => setCostBasis(e.target.value)}
                    placeholder="450000"
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Current value</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={currentValue}
                    onChange={(e) => setCurrentValue(e.target.value)}
                    placeholder="525000"
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400"
                  />
                </div>
              </div>
            )}

            <div className="flex justify-end pt-2">
              <button
                type="submit"
                disabled={submitting}
                className="px-5 py-2 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50 transition"
              >
                {submitting ? "Adding..." : "Add holding"}
              </button>
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
          </form>
        </div>

        {market.length > 0 && (
          <HoldingsSection
            title="Investments"
            holdings={market}
            onDelete={handleDelete}
          />
        )}
        {options.length > 0 && (
          <HoldingsSection
            title="Options"
            holdings={options}
            onDelete={handleDelete}
            kind="option"
          />
        )}
        {assets.length > 0 && (
          <HoldingsSection
            title="Other assets"
            holdings={assets}
            onDelete={handleDelete}
            kind="asset"
          />
        )}
        {!loading && holdings.length === 0 && (
          <div className="text-center text-gray-400 py-12 border border-gray-200 rounded-2xl">
            No holdings yet. Add your first above.
          </div>
        )}
      </div>
    </div>
  );
}

function HoldingsSection({
  title,
  holdings,
  onDelete,
  kind = "market",
}: {
  title: string;
  holdings: Holding[];
  onDelete: (id: string) => void;
  kind?: FormKind;
}) {
  const isAsset = kind === "asset";
  const isOption = kind === "option";
  return (
    <div className="border border-gray-200 rounded-2xl overflow-hidden mb-6">
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 text-sm font-semibold text-gray-700">
        {title}
      </div>
      <table className="w-full text-sm">
        <thead className="bg-white border-b border-gray-200">
          <tr className="text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
            <th className="px-4 py-3">{isAsset ? "Asset" : isOption ? "Contract" : "Symbol"}</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3 text-right">{isAsset ? "" : isOption ? "Contracts" : "Qty"}</th>
            <th className="px-4 py-3 text-right">
              {isAsset ? "Purchase price" : isOption ? "Premium $/sh" : "Cost / share"}
            </th>
            {isAsset && <th className="px-4 py-3 text-right">Current value</th>}
            {isOption && <th className="px-4 py-3 text-right">Total premium</th>}
            <th className="px-4 py-3 text-right"></th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => (
            <tr key={h.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
              <td className="px-4 py-3">
                <div className="font-medium text-gray-900">
                  {isAsset || isOption ? (h.name || h.symbol) : h.symbol}
                </div>
                {!isAsset && !isOption && h.name && (
                  <div className="text-xs text-gray-500 truncate max-w-[200px]">{h.name}</div>
                )}
              </td>
              <td className="px-4 py-3 text-xs text-gray-600">
                {TYPE_LABEL[h.security_type] || h.security_type}
              </td>
              <td className="px-4 py-3 text-right tabular-nums">
                {isAsset ? "" : h.quantity}
              </td>
              <td className="px-4 py-3 text-right tabular-nums">
                ${Number(h.cost_basis).toFixed(2)}
              </td>
              {isAsset && (
                <td className="px-4 py-3 text-right tabular-nums">
                  ${Number(h.current_value || 0).toLocaleString()}
                </td>
              )}
              {isOption && (
                <td className="px-4 py-3 text-right tabular-nums">
                  ${(Number(h.quantity) * Number(h.cost_basis) * 100).toLocaleString()}
                </td>
              )}
              <td className="px-4 py-3 text-right">
                <button
                  onClick={() => onDelete(h.id)}
                  className="text-xs text-red-600 hover:text-red-800 transition"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
