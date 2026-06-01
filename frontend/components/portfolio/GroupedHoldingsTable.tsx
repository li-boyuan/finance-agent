import {
  HoldingGroup,
  HoldingRow,
  buildGroups,
  colorClass,
  fmtCurrency,
  fmtPct,
  TYPE_BADGE,
} from "./grouping";

// Shared grouped-by-underlying holdings table. Read-only by default; pass
// onDelete to render a trailing actions column (used by the holdings manager).
export function GroupedHoldingsTable({
  holdings,
  onDelete,
}: {
  holdings: HoldingRow[];
  onDelete?: (id: string) => void;
}) {
  const groups = buildGroups(holdings);
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
          const showHeader = g.rows.length > 1 || g.key === "__assets__";
          return (
            <GroupRows
              key={g.key}
              group={g}
              showHeader={showHeader}
              onDelete={onDelete}
            />
          );
        })}
      </tbody>
    </table>
  );
}

function GroupRows({
  group,
  showHeader,
  onDelete,
}: {
  group: HoldingGroup;
  showHeader: boolean;
  onDelete?: (id: string) => void;
}) {
  return (
    <>
      {showHeader && (
        <tr className="bg-gray-50 border-b border-gray-200">
          <td className="px-4 py-2.5">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-gray-900">{group.label}</span>
              <span className="text-xs text-gray-500">
                {group.rows.length} position{group.rows.length === 1 ? "" : "s"}
              </span>
            </div>
          </td>
          <td colSpan={2}></td>
          <td className={`px-4 py-2.5 text-right tabular-nums text-xs ${colorClass(group.totalDayChange)}`}>
            {fmtCurrency(group.totalDayChange)}
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
      {group.rows.map((h) => (
        <HoldingTableRow
          key={h.id}
          holding={h}
          indented={showHeader}
          onDelete={onDelete}
        />
      ))}
    </>
  );
}

function HoldingTableRow({
  holding: h,
  indented,
  onDelete,
}: {
  holding: HoldingRow;
  indented: boolean;
  onDelete?: (id: string) => void;
}) {
  const displayName = h.is_option ? (h.name || h.symbol) : (h.is_market ? h.symbol : h.name);
  return (
    <tr className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
      <td className={`px-4 py-3 ${indented ? "pl-8" : ""}`}>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-gray-900">{displayName}</span>
          <span className="text-[10px] font-semibold bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
            {TYPE_BADGE[h.security_type] || h.security_type.slice(0, 3).toUpperCase()}
          </span>
          {h.is_short && (
            <span className="text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded">
              SHORT
            </span>
          )}
        </div>
        {h.is_market && !h.is_option && h.name && (
          <div className="text-xs text-gray-500 truncate max-w-[220px]">{h.name}</div>
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
