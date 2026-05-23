"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
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

  const sendMessage = async () => {
    if (!token || !input.trim() || sending) return;
    const userMessage: Message = { role: "user", content: input };
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

  return (
    <div className="flex h-screen">
      <div className="w-64 border-r border-gray-200 bg-gray-50 flex flex-col">
        <div className="p-4 border-b border-gray-200">
          <button
            onClick={newConversation}
            className="w-full px-3 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            + New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => loadConversation(c.id)}
              className={`w-full text-left px-4 py-3 text-sm hover:bg-gray-100 border-b border-gray-100 truncate ${
                c.id === activeConvId ? "bg-gray-200" : ""
              }`}
            >
              {c.title || "Untitled"}
            </button>
          ))}
        </div>
        <div className="border-t border-gray-200 p-3">
          <button
            onClick={() => setShowAbout(!showAbout)}
            className="w-full text-left text-sm text-gray-700 hover:text-gray-900"
          >
            About you
          </button>
        </div>
      </div>

      <div className="flex-1 flex flex-col">
        {showAbout ? (
          <div className="flex-1 p-8 overflow-y-auto">
            <h2 className="text-xl font-semibold mb-2">About your finances</h2>
            <p className="text-sm text-gray-600 mb-4">
              Tell the advisor about your income, debts, savings, goals, and
              constraints. This stays private and helps every answer be
              personalized.
            </p>
            <textarea
              value={financialContext}
              onChange={(e) => setFinancialContext(e.target.value)}
              rows={16}
              className="w-full p-3 border border-gray-300 rounded font-mono text-sm"
              placeholder="e.g. I'm 32, make $120k/yr, have $30k in 401k (5% match), $15k student loans at 6%, $20k emergency fund. Want to buy a $500k house in 2 years."
            />
            <div className="mt-4 flex gap-2">
              <button
                onClick={saveFinancialContext}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Save
              </button>
              <button
                onClick={() => setShowAbout(false)}
                className="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {messages.length === 0 && !streamingContent && (
                <div className="text-center text-gray-500 mt-20">
                  <p className="text-lg mb-2">Ask anything about your money.</p>
                  <p className="text-sm">
                    Budgeting · Debt · Investing · Retirement · Major purchases
                  </p>
                </div>
              )}
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`flex ${
                    m.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  <div
                    className={`max-w-2xl px-4 py-3 rounded-lg whitespace-pre-wrap ${
                      m.role === "user"
                        ? "bg-blue-600 text-white"
                        : "bg-gray-100 text-gray-900"
                    }`}
                  >
                    {m.content}
                  </div>
                </div>
              ))}
              {streamingContent && (
                <div className="flex justify-start">
                  <div className="max-w-2xl px-4 py-3 rounded-lg bg-gray-100 text-gray-900 whitespace-pre-wrap">
                    {streamingContent}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <div className="border-t border-gray-200 p-4">
              <div className="flex gap-2 max-w-4xl mx-auto">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                  disabled={sending}
                  placeholder="Ask your finance advisor..."
                  className="flex-1 px-4 py-3 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  onClick={sendMessage}
                  disabled={sending || !input.trim()}
                  className="px-6 py-3 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                >
                  Send
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
