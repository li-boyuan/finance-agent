import Link from "next/link";

const STEPS = [
  {
    n: "1",
    title: "Sign up",
    body: "Free, no credit card. Email and password — that's it.",
  },
  {
    n: "2",
    title: "Tell it about you",
    body: "Your income, debts, goals, anything that matters. Or skip and start asking.",
  },
  {
    n: "3",
    title: "Ask anything",
    body: "Get clear, math-correct answers tailored to your actual situation.",
  },
];

const FEATURES = [
  {
    title: "Plain English",
    body: "No jargon, no platitudes. Concrete numbers, clear tradeoffs, real recommendations.",
  },
  {
    title: "Knows you",
    body: "Your income, debts, and goals are factored into every answer — not generic advice.",
  },
  {
    title: "Long-form reasoning",
    body: "Powered by Claude Sonnet 4.6. Handles multi-step decisions, asks clarifying questions, shows its work.",
  },
  {
    title: "Real accounts (coming)",
    body: "Soon: link your bank and brokerage via Plaid. Answers grounded in your actual transactions and holdings.",
  },
];

const FAQS = [
  {
    q: "Is this financial advice?",
    a: "No. Finance Agent is an informational tool, not a licensed financial advisor or tax professional. For binding decisions (filing taxes, signing legal documents, complex estate planning), consult a qualified professional.",
  },
  {
    q: "How is this different from ChatGPT?",
    a: "Built specifically for personal finance: remembers your situation across conversations, will soon ground answers in your real account data, and is tuned for the kinds of tradeoffs money decisions actually involve.",
  },
  {
    q: "What about my data?",
    a: "Stored in Supabase with row-level security — only you can read your own data. Sensitive tokens are encrypted at rest. We never sell or share your data. You can delete your account anytime.",
  },
  {
    q: "What does it cost?",
    a: "Free while we build. Paid plans will arrive alongside bank linking; existing accounts keep current features.",
  },
];

export default function Home() {
  return (
    <main className="bg-white text-gray-900 min-h-screen">
      {/* Top nav */}
      <nav className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-emerald-600 flex items-center justify-center text-white text-xs font-semibold">
            FA
          </div>
          <span className="font-semibold">Finance Agent</span>
        </div>
        <div className="flex items-center gap-6 text-sm">
          <Link href="/login" className="text-gray-700 hover:text-gray-900">
            Sign in
          </Link>
          <Link
            href="/login"
            className="bg-gray-900 text-white px-4 py-2 rounded-lg hover:bg-gray-800 transition"
          >
            Get started
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-4xl mx-auto px-6 pt-16 pb-24 text-center">
        <h1 className="text-5xl sm:text-6xl font-semibold tracking-tight leading-tight">
          A personal finance copilot that{" "}
          <span className="text-emerald-600">actually knows you</span>.
        </h1>
        <p className="mt-6 text-xl text-gray-600 max-w-2xl mx-auto leading-relaxed">
          Tell it your situation. Ask anything about money. Get plain-English,
          math-correct guidance grounded in your real numbers.
        </p>
        <div className="mt-10 flex items-center justify-center gap-4">
          <Link
            href="/login"
            className="bg-gray-900 text-white text-lg font-medium px-7 py-3.5 rounded-lg hover:bg-gray-800 transition"
          >
            Try it free
          </Link>
          <Link
            href="#how-it-works"
            className="text-gray-700 text-lg font-medium px-7 py-3.5 hover:text-gray-900 transition"
          >
            How it works →
          </Link>
        </div>
        <p className="mt-4 text-sm text-gray-500">
          Free while we build · No credit card · Cancel anytime
        </p>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="bg-gray-50 border-y border-gray-200">
        <div className="max-w-5xl mx-auto px-6 py-20">
          <h2 className="text-3xl font-semibold text-center mb-2">How it works</h2>
          <p className="text-center text-gray-600 mb-12">
            Three steps to a finance copilot tuned to your life.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {STEPS.map((s) => (
              <div key={s.n} className="text-center">
                <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-emerald-600 text-white flex items-center justify-center text-lg font-semibold">
                  {s.n}
                </div>
                <h3 className="text-xl font-semibold mb-2">{s.title}</h3>
                <p className="text-gray-600 leading-relaxed">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-5xl mx-auto px-6 py-20">
        <h2 className="text-3xl font-semibold text-center mb-2">What makes it different</h2>
        <p className="text-center text-gray-600 mb-12">
          Not a chatbot bolted onto finance. Built for the kinds of decisions money actually requires.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="border border-gray-200 rounded-2xl p-6 hover:border-gray-300 transition"
            >
              <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
              <p className="text-gray-600 leading-relaxed">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Trust */}
      <section className="bg-gray-50 border-y border-gray-200">
        <div className="max-w-3xl mx-auto px-6 py-20 text-center">
          <h2 className="text-3xl font-semibold mb-6">Built with your money in mind</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 mt-10 text-left">
            <div>
              <h3 className="font-semibold mb-2">Encrypted at rest</h3>
              <p className="text-gray-600 text-sm leading-relaxed">
                Any connected-account tokens are encrypted before they touch the database.
              </p>
            </div>
            <div>
              <h3 className="font-semibold mb-2">Row-level security</h3>
              <p className="text-gray-600 text-sm leading-relaxed">
                Postgres RLS enforces that only you can read your own data — at the database layer, not just the app.
              </p>
            </div>
            <div>
              <h3 className="font-semibold mb-2">Read-only by design</h3>
              <p className="text-gray-600 text-sm leading-relaxed">
                When bank linking arrives, accounts will be read-only. Finance Agent can&apos;t move your money.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="max-w-3xl mx-auto px-6 py-20">
        <h2 className="text-3xl font-semibold text-center mb-12">Frequently asked</h2>
        <div className="space-y-6">
          {FAQS.map((f) => (
            <div key={f.q} className="border-b border-gray-200 pb-6 last:border-0">
              <h3 className="text-lg font-semibold mb-2">{f.q}</h3>
              <p className="text-gray-600 leading-relaxed">{f.a}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section className="bg-gray-900 text-white">
        <div className="max-w-3xl mx-auto px-6 py-20 text-center">
          <h2 className="text-3xl sm:text-4xl font-semibold mb-4">
            Stop Googling. Start asking.
          </h2>
          <p className="text-lg text-gray-300 mb-8">
            Sign up and have your first finance conversation in under a minute.
          </p>
          <Link
            href="/login"
            className="inline-block bg-white text-gray-900 text-lg font-medium px-7 py-3.5 rounded-lg hover:bg-gray-100 transition"
          >
            Try it free
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-200">
        <div className="max-w-6xl mx-auto px-6 py-10 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <div className="w-5 h-5 rounded-full bg-emerald-600 flex items-center justify-center text-white text-[10px] font-semibold">
              FA
            </div>
            <span>© 2026 Finance Agent</span>
          </div>
          <p className="text-xs text-gray-500 text-center sm:text-right max-w-md leading-relaxed">
            Finance Agent provides informational guidance, not professional financial, tax, or legal advice. Consult a qualified professional for binding decisions.
          </p>
        </div>
      </footer>
    </main>
  );
}
