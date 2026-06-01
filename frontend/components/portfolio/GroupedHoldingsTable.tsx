"use client";

import { useState } from "react";
import {
  HoldingGroup,
  HoldingRow,
  buildGroups,
  colorClass,
  fmtCurrency,
  fmtPct,
  TYPE_BADGE,
} from "./grouping";

// Shared grouped-by-underlying holdings table.
//   onDelete    — renders a trailing actions column (holdings manager).
//   collapsible — group rows start collapsed and expand on click (portfolio
//                 overview). A group gets a header when it has >1 position, is
//                 the assets bucket, or (collapsible) is a lone option — so a
//                 single option still shows under its underlying ticker.
export function GroupedHoldingsTable({
  holdings,
  onDelete,
  collapsible = false,
}: {
  holdings: HoldingRow[];
  onDelete?: (id: string) => void;
  collapsible?: boolean;
}) {
  const groups = buildGroups(holdings);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <table className="w-full text-sm">
      <thead className="bg-gray-50 border-b border-gray-200">
        <tr className="text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
          <th className="px-4 py-3">Symbol</th>
          <th className="px-4 py-3 text-right">Qty</th>
          <th className="px-4 py-3 text-right">Price</th>
          <th className="px-4 py-3 text-right">Day</th>
          <th className="px-4 py-3 text-right">Value</th>
          <th className="px-4 py-3 text-right">Return</th>
          {onDelete && <th className="px-4 py-3"></th>}
        </tr>
      </thead>
      <tbody>
        {groups.map((g) => {
          const loneOption =
            g.rows.length === 1 && !!g.rows[0].is_option;
          const hasHeader =
            g.rows.length > 1 ||
            g.key === "__assets__" ||
            (collapsible && loneOption);
          const expandable = collapsible && hasHeader;
          // Single-position groups (no header) always show their one row.
          const showChildren = !expandable || expanded.has(g.key);
          return (
            <GroupRows
              key={g.key}
              group={g}
              showHeader={hasHeader}
              collapsible={collapsible}
              onDelete={onDelete}
              expandable={expandable}
              expanded={expanded.has(g.key)}
              onToggle={() => toggle(g.key)}
              showChildren={showChildren}
            />
          );
        })}
      </tbody>
    </table>
  );
}

function Caret({ expanded }: { expanded: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden
      className="shrink-0 text-gray-400 transition-transform duration-200 ease-out"
      style={{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)" }}
    >
      <path
        d="M6 4l4 4-4 4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function GroupRows({
  group,
  showHeader,
  collapsible,
  onDelete,
  expandable,
  expanded,
  onToggle,
  showChildren,
}: {
  group: HoldingGroup;
  showHeader: boolean;
  collapsible: boolean;
  onDelete?: (id: string) => void;
  expandable: boolean;
  expanded: boolean;
  onToggle: () => void;
  showChildren: boolean;
}) {
  return (
    <>
      {showHeader && (
        <tr
          className={`border-b border-gray-200 transition-colors ${expandable ? "cursor-pointer hover:bg-gray-50" : "bg-gray-50"}`}
          onClick={expandable ? onToggle : undefined}
        >
          <td className="px-4 py-2.5">
            <div className="flex items-center gap-2">
              {expandable && <Caret expanded={expanded} />}
              <span className="font-semibold text-gray-900">{group.label}</span>
              <span className="text-xs text-gray-500">
                {group.rows.length} position{group.rows.length === 1 ? "" : "s"}
              </span>
            </div>
          </td>
          <td colSpan={2}></td>
          <td className={`px-4 py-2.5 text-right tabular-nums font-semibold ${colorClass(group.totalDayChange)}`}>
            {fmtPct(group.totalDayChangePct)}
          </td>
          <td className="px-4 py-2.5 text-right tabular-nums font-semibold">
            {fmtCurrency(group.totalValue)}
          </td>
          <td className={`px-4 py-2.5 text-right tabular-nums font-semibold ${colorClass(group.totalReturn)}`}>
            {fmtPct(group.totalReturnPct)}
          </td>
          {onDelete && <td></td>}
        </tr>
      )}
      {showChildren &&
        group.rows.map((h, i) => (
          <HoldingTableRow
            key={h.id}
            holding={h}
            indented={showHeader}
            // Top-level single-position rows in collapsible mode get a gutter so
            // their ticker lines up with the chevroned group rows (siblings).
            leadSpacer={collapsible && !showHeader}
            animateIn={expandable}
            animateIndex={i}
            onDelete={onDelete}
          />
        ))}
    </>
  );
}

function HoldingTableRow({
  holding: h,
  indented,
  leadSpacer = false,
  animateIn = false,
  animateIndex = 0,
  onDelete,
}: {
  holding: HoldingRow;
  indented: boolean;
  leadSpacer?: boolean;
  animateIn?: boolean;
  animateIndex?: number;
  onDelete?: (id: string) => void;
}) {
  const displayName = h.is_option ? (h.name || h.symbol) : (h.is_market ? h.symbol : h.name);
  return (
    <tr
      className={`border-b border-gray-100 last:border-0 hover:bg-gray-50 ${animateIn ? "animate-row-in" : ""}`}
      style={animateIn ? { animationDelay: `${animateIndex * 35}ms` } : undefined}
    >
      <td className={`px-4 py-3 ${indented ? "pl-8" : ""}`}>
        <div className="flex items-center gap-2 flex-wrap">
          {leadSpacer && <span className="w-3.5 inline-block" aria-hidden />}
          <span className={`${leadSpacer ? "font-semibold" : "font-medium"} text-gray-900`}>
            {displayName}
          </span>
          <span className="text-[10px] font-semibold bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
            {TYPE_BADGE[h.security_type] || h.security_type.slice(0, 3).toUpperCase()}
          </span>
          {h.provider && h.provider !== "manual" && (
            <span className="text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 px-1.5 py-0.5 rounded">
              {h.provider === "ibkr" ? "IBKR" : h.provider === "plaid" ? "FID" : h.provider.toUpperCase()}
            </span>
          )}
          {h.is_short && (
            <span className="text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded">
              SHORT
            </span>
          )}
        </div>
        {h.is_market && !h.is_option && h.name && (
          <div className={`text-xs text-gray-500 truncate max-w-[220px] ${leadSpacer ? "pl-[22px]" : ""}`}>
            {h.name}
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-gray-700">
        {h.is_market ? h.quantity : "—"}
      </td>
      <td className="px-4 py-3 text-right tabular-nums">
        {h.is_market ? (h.quote_available ? fmtCurrency(h.price) : "—") : "—"}
      </td>
      <td className={`px-4 py-3 text-right tabular-nums ${h.is_market ? colorClass(h.day_change) : "text-gray-400"}`}>
        {h.is_market ? (h.quote_available ? fmtPct(h.day_change_pct) : "—") : "—"}
      </td>
      <td className="px-4 py-3 text-right tabular-nums">
        {fmtCurrency(h.value)}
      </td>
      <td className={`px-4 py-3 text-right tabular-nums ${colorClass(h.total_return)}`}>
        {fmtPct(h.total_return_pct)}
      </td>
      {onDelete && (
        <td className="px-4 py-3 text-right">
          <button
            onClick={() => onDelete(h.id)}
            className="text-xs text-red-600 hover:text-red-800 transition"
          >
            Delete
          </button>
        </td>
      )}
    </tr>
  );
}
