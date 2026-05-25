"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Message {
  id?: string;
  role: "user" | "assistant";
  content: string;
}

interface Conversation {
  id: string;
  title: string | null;
  updated_at: string;
}

const STARTER_PROMPTS = [
  { title: "Should I prioritize", subtitle: "paying off debt or investing?" },
  { title: "Build me a budget", subtitle: "for next month from my situation" },
  { title: "Am I on track", subtitle: "for retirement?" },
  { title: "Explain Roth vs Traditional", subtitle: "for my income bracket" },
];

function groupConversations(conversations: Conversation[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const sevenDaysAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: Record<string, Conversation[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 days": [],
    Older: [],
  };
  for (const c of conversations) {
    const d = new Date(c.updated_at);
    if (d >= today) groups.Today.push(c);
    else if (d >= yesterday) groups.Yesterday.push(c);
    else if (d >= sevenDaysAgo) groups["Previous 7 days"].push(c);
    else groups.Older.push(c);
  }
  return groups;
}

export default function ChatPage() {
  const router = useRouter();
  const supabase = createClient();
  const [token, setToken] = useState<string>("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [financialContext, setFinancialContext] = useState("");
  const [showAbout, setShowAbout] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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

  const fetchConversations = useCallback(async () => {
    if (!token) return;
    const res = await fetch(`${API_URL}/api/chat/conversations`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data = await res.json();
      setConversations(data.conversations || []);
    }
  }, [token]);

  const fetchProfile = useCallback(async () => {
    if (!token) return;
    const res = await fetch(`${API_URL}/api/profile/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data = await res.json();
      setFinancialContext(data.financial_context || "");
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      fetchConversations();
      fetchProfile();
    }
  }, [token, fetchConversations, fetchProfile]);

  const loadConversation = async (convId: string) => {
    if (!token) return;
    const res = await fetch(
      `${API_URL}/api/chat/conversations/${convId}/messages`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (res.ok) {
      const data = await res.json();
      setActiveConvId(convId);
      setMessages(data.messages || []);
      setStreamingContent("");
    }
  };

  const newConversation = () => {
    setActiveConvId(null);
    setMessages([]);
    setStreamingContent("");
    textareaRef.current?.focus();
  };

  const saveFinancialContext = async () => {
    if (!token) return;
    await fetch(`${API_URL}/api/profile/`, {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ financial_context: financialContext }),
    });
    setShowAbout(false);
  };

  const sendMessage = async (overrideText?: string) => {
    const text = overrideText ?? input;
    if (!token || !text.trim() || sending) return;
    const userMessage: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setSending(true);
    setStreamingContent("");

    try {
      const res = await fetch(`${API_URL}/api/chat/messages`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          conversation_id: activeConvId,
          content: userMessage.content,
        }),
      });

      if (!res.ok || !res.body) {
        throw new Error(`Request failed: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistantContent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const evt of events) {
          if (!evt.startsWith("data: ")) continue;
          const data = JSON.parse(evt.slice(6));
          if (data.type === "conversation") {
            setActiveConvId(data.conversation_id);
          } else if (data.type === "text") {
            assistantContent += data.text;
            setStreamingContent(assistantContent);
          } else if (data.type === "done") {
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: assistantContent },
            ]);
            setStreamingContent("");
            fetchConversations();
          } else if (data.type === "error") {
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: `Error: ${data.message}` },
            ]);
            setStreamingContent("");
          }
        }
      }
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${(e as Error).message}` },
      ]);
      setStreamingContent("");
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const groups = groupConversations(conversations);
  const showEmpty = messages.length === 0 && !streamingContent && !showAbout;

  return (
    <div className="flex h-full bg-white text-gray-900">
      <aside className="w-[260px] flex-shrink-0 border-r border-gray-200 bg-gray-50 flex flex-col">
        <div className="p-3">
          <button
            onClick={newConversation}
            className="w-full flex items-center gap-2 px-3 py-2.5 text-sm font-medium text-gray-800 border border-gray-200 bg-white rounded-lg hover:bg-gray-100 transition"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2">
          {Object.entries(groups).map(([label, items]) =>
            items.length > 0 ? (
              <div key={label} className="mb-4">
                <div className="px-3 py-1 text-xs font-medium text-gray-500 uppercase tracking-wide">
                  {label}
                </div>
                {items.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => loadConversation(c.id)}
                    className={`w-full text-left px-3 py-2 text-sm rounded-lg truncate transition ${
                      c.id === activeConvId
                        ? "bg-gray-200 text-gray-900"
                        : "text-gray-700 hover:bg-gray-100"
                    }`}
                  >
                    {c.title || "Untitled"}
                  </button>
                ))}
              </div>
            ) : null,
          )}
        </div>
        <div className="border-t border-gray-200 p-2">
          <button
            onClick={() => setShowAbout(!showAbout)}
            className="w-full flex items-center gap-3 px-3 py-2 text-sm text-gray-700 rounded-lg hover:bg-gray-100 transition"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="8" r="4" />
              <path d="M4 21v-1a8 8 0 0 1 16 0v1" />
            </svg>
            About you
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0">
        {showAbout ? (
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-3xl mx-auto p-8">
              <h2 className="text-2xl font-semibold mb-2">About your finances</h2>
              <p className="text-sm text-gray-600 mb-6">
                Tell the advisor about your income, debts, savings, goals, and
                constraints. This stays private and makes every answer
                personalized.
              </p>
              <textarea
                value={financialContext}
                onChange={(e) => setFinancialContext(e.target.value)}
                rows={14}
                className="w-full p-4 border border-gray-300 rounded-xl text-sm text-gray-900 focus:outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-400 resize-none"
                placeholder="e.g. I'm 32, single, make $140k/yr in tech. $40k in 401k (5% match, fully captured), $20k Roth IRA, $25k emergency fund, $12k student loans at 6.5%, no credit card debt. Want to buy a $600k condo in 18 months."
              />
              <div className="mt-4 flex gap-2">
                <button
                  onClick={saveFinancialContext}
                  className="px-5 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 transition"
                >
                  Save
                </button>
                <button
                  onClick={() => setShowAbout(false)}
                  className="px-5 py-2.5 border border-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 transition"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto">
              {showEmpty ? (
                <div className="h-full flex flex-col items-center justify-center px-4">
                  <h1 className="text-3xl font-semibold mb-2 text-gray-900">
                    How can I help with your money?
                  </h1>
                  <p className="text-sm text-gray-500 mb-12">
                    Budgeting · Debt · Investing · Retirement · Major decisions
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
                    {STARTER_PROMPTS.map((p, i) => (
                      <button
                        key={i}
                        onClick={() => sendMessage(`${p.title} ${p.subtitle}`)}
                        className="text-left p-4 border border-gray-200 rounded-xl hover:bg-gray-50 transition"
                      >
                        <div className="text-sm font-medium text-gray-900">
                          {p.title}
                        </div>
                        <div className="text-sm text-gray-500 mt-0.5">
                          {p.subtitle}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="max-w-3xl mx-auto px-6 py-8 space-y-8">
                  {messages.map((m, i) => (
                    <MessageView key={i} role={m.role} content={m.content} />
                  ))}
                  {streamingContent && (
                    <MessageView role="assistant" content={streamingContent} />
                  )}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </div>

            <div className="border-t border-gray-200 bg-white">
              <div className="max-w-3xl mx-auto p-4">
                <div className="flex items-end gap-2 border border-gray-300 rounded-3xl px-4 py-3 focus-within:border-gray-400 focus-within:ring-1 focus-within:ring-gray-400">
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={sending}
                    rows={1}
                    placeholder="Ask anything about your money..."
                    className="flex-1 resize-none bg-transparent text-gray-900 placeholder-gray-400 focus:outline-none max-h-40"
                    style={{ minHeight: "24px" }}
                  />
                  <button
                    onClick={() => sendMessage()}
                    disabled={sending || !input.trim()}
                    className="flex-shrink-0 w-8 h-8 flex items-center justify-center bg-gray-900 text-white rounded-full hover:bg-gray-800 disabled:bg-gray-300 disabled:cursor-not-allowed transition"
                    aria-label="Send"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 19V5M5 12l7-7 7 7" />
                    </svg>
                  </button>
                </div>
                <p className="text-xs text-gray-400 text-center mt-2">
                  Finance Agent provides informational guidance, not professional financial, tax, or legal advice.
                </p>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function MessageView({ role, content }: { role: "user" | "assistant"; content: string }) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] bg-gray-100 text-gray-900 rounded-2xl px-4 py-3 whitespace-pre-wrap">
          {content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-emerald-600 flex items-center justify-center text-white text-xs font-semibold">
        FA
      </div>
      <div className="flex-1 text-gray-900 leading-relaxed">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
            ul: ({ children }) => <ul className="list-disc pl-6 mb-3 space-y-1">{children}</ul>,
            ol: ({ children }) => <ol className="list-decimal pl-6 mb-3 space-y-1">{children}</ol>,
            li: ({ children }) => <li>{children}</li>,
            strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
            code: ({ children }) => (
              <code className="bg-gray-100 text-gray-800 px-1.5 py-0.5 rounded text-sm font-mono">
                {children}
              </code>
            ),
            pre: ({ children }) => (
              <pre className="bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-x-auto text-sm font-mono mb-3">
                {children}
              </pre>
            ),
            table: ({ children }) => (
              <div className="overflow-x-auto my-3">
                <table className="min-w-full text-sm border-collapse">{children}</table>
              </div>
            ),
            th: ({ children }) => (
              <th className="border border-gray-300 bg-gray-50 px-3 py-1.5 text-left font-semibold">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="border border-gray-300 px-3 py-1.5">{children}</td>
            ),
            h1: ({ children }) => <h1 className="text-xl font-semibold mt-4 mb-2">{children}</h1>,
            h2: ({ children }) => <h2 className="text-lg font-semibold mt-4 mb-2">{children}</h2>,
            h3: ({ children }) => <h3 className="text-base font-semibold mt-3 mb-2">{children}</h3>,
            blockquote: ({ children }) => (
              <blockquote className="border-l-4 border-gray-300 pl-4 italic text-gray-700 my-3">
                {children}
              </blockquote>
            ),
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noopener noreferrer" className="text-emerald-700 underline">
                {children}
              </a>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
}
