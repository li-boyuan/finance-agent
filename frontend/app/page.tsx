import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 p-8">
      <div className="text-center">
        <h1 className="text-5xl font-bold tracking-tight">TradeLog</h1>
        <p className="mt-4 text-lg text-gray-400">
          Auto-capture trades from IBKR. Analyze your edge.
        </p>
      </div>
      <div className="flex gap-4">
        <Link
          href="/login"
          className="rounded-lg bg-blue-600 px-6 py-3 font-medium hover:bg-blue-500 transition"
        >
          Get Started
        </Link>
      </div>
    </main>
  );
}
