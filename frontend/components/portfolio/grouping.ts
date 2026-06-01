export interface OptionMeta {
  underlying: string;
  expiry: string;
  strike: number;
  option_type: "C" | "P";
}

export interface HoldingRow {
  id: string;
  symbol: string;
  name: string;
  security_type: string;
  is_market: boolean;
  is_option?: boolean;
  is_short?: boolean;
  option_meta?: OptionMeta | null;
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

export interface HoldingGroup {
  key: string;        // grouping key (underlying ticker, or "__assets__" / "__other__")
  label: string;      // display label
  rows: HoldingRow[]; // child rows
  totalValue: number;
  totalCost: number;
  totalReturn: number;
  totalReturnPct: number;
  totalDayChange: number;
  totalDayChangePct: number;
}

export interface PortfolioSummary {
  total_value: number;
  total_cost: number;
  total_return: number;
  total_return_pct: number;
  today_change: number;
  today_change_pct: number;
  positions_count: number;
  holdings: HoldingRow[];
}

export const TYPE_BADGE: Record<string, string> = {
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

// Symbols that should display under another group — e.g. a leveraged ETF shown
// with the underlying it tracks. Applied to the grouping key only; each holding
// keeps its own real symbol, price, and P&L.
const GROUP_ALIASES: Record<string, string> = {
  HIMZ: "HIMS", // Defiance Daily Target 2x Long HIMS ETF → group under HIMS
};

export function groupingKey(h: HoldingRow): string {
  const raw =
    h.is_option && h.option_meta
      ? h.option_meta.underlying
      : h.is_market
        ? h.symbol
        : "__assets__";
  return GROUP_ALIASES[raw] ?? raw;
}

export function buildGroups(holdings: HoldingRow[]): HoldingGroup[] {
  const buckets: Record<string, HoldingRow[]> = {};
  for (const h of holdings) {
    const key = groupingKey(h);
    (buckets[key] = buckets[key] || []).push(h);
  }
  const groups: HoldingGroup[] = Object.entries(buckets).map(([key, rows]) => {
    // Sort children: stock first, then options sorted by expiry then strike.
    rows.sort((a: HoldingRow, b: HoldingRow) => {
      if (!!a.is_option !== !!b.is_option) return a.is_option ? 1 : -1;
      if (a.is_option && b.is_option) {
        const ea = a.option_meta?.expiry || "";
        const eb = b.option_meta?.expiry || "";
        if (ea !== eb) return ea.localeCompare(eb);
        return (a.option_meta?.strike || 0) - (b.option_meta?.strike || 0);
      }
      return a.symbol.localeCompare(b.symbol);
    });
    const totalValue = rows.reduce((s: number, r: HoldingRow) => s + r.value, 0);
    const totalCost = rows.reduce((s: number, r: HoldingRow) => s + r.cost_total, 0);
    const totalReturn = rows.reduce((s: number, r: HoldingRow) => s + r.total_return, 0);
    const totalDayChange = rows.reduce((s: number, r: HoldingRow) => s + r.day_change, 0);
    const totalReturnPct = totalCost ? (totalReturn / Math.abs(totalCost)) * 100 : 0;
    // Group day % = today's net $ change over yesterday's net value (totalValue - totalDayChange).
    const totalPrevValue = totalValue - totalDayChange;
    const totalDayChangePct = totalPrevValue ? (totalDayChange / Math.abs(totalPrevValue)) * 100 : 0;
    const label = key === "__assets__" ? "Other Assets" : key;
    return {
      key, label, rows,
      totalValue, totalCost, totalReturn, totalReturnPct, totalDayChange, totalDayChangePct,
    };
  });
  // Sort groups by absolute exposure so big shorts stay near the top.
  groups.sort((a, b) => Math.abs(b.totalValue) - Math.abs(a.totalValue));
  return groups;
}

export function fmtCurrency(n: number) {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export function fmtPct(n: number) {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

export function colorClass(n: number) {
  if (n > 0) return "text-emerald-600";
  if (n < 0) return "text-red-600";
  return "text-gray-500";
}
