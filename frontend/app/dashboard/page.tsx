import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return (
    <main className="min-h-screen p-8">
      <header className="flex items-center justify-between border-b border-gray-800 pb-4">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <span className="text-sm text-gray-400">{user.email}</span>
      </header>

      <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Today P&L" value="--" />
        <StatCard label="Win Rate" value="--" />
        <StatCard label="Total Trades" value="0" />
        <StatCard label="IBKR Status" value="Not Connected" />
      </div>

      <section className="mt-10">
        <h2 className="text-lg font-semibold mb-4">Recent Trades</h2>
        <div className="rounded-lg border border-gray-800 p-8 text-center text-gray-500">
          Connect your IBKR account to start importing trades.
        </div>
      </section>
    </main>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-800 p-5">
      <p className="text-sm text-gray-400">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
    </div>
  );
}
