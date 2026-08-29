"use client";

import { useEffect, useRef, useState } from "react";

import Markdown from "@/components/Markdown";
import { ChevronIcon, SparkIcon } from "@/components/icons";
import { sendChat } from "@/lib/api";
import { parseBudget } from "@/lib/budget";

interface Message {
  id: string;
  role: "user" | "agent" | "error";
  text: string;
  tools?: string[];
  seconds?: number;
}

const SUGGESTIONS = [
  "I have $500,000 for Central LA. Where should I invest?",
  "Why does night-time heat matter more than the afternoon peak?",
  "What would $1,200,000 buy me?",
];

/**
 * The tool trace, folded away by default.
 *
 * Expanded, four or five function names wrap onto three lines and dominate the
 * answer they belong to. Collapsed, the count still tells the reader the number
 * came from a tool call rather than the language model - which is the point the
 * chips were there to make - and the names stay one click away.
 */
function ToolTrace({ tools, seconds }: { tools: string[]; seconds?: number }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-2 border-t border-slate-200 pt-2">
      <button
        type="button"
        onClick={() => setOpen((was) => !was)}
        aria-expanded={open}
        className="flex w-full items-center gap-1 text-[10px] font-medium text-slate-400 transition hover:text-slate-700"
      >
        <ChevronIcon
          className={`h-3 w-3 transition-transform duration-200 ${open ? "rotate-90" : ""}`}
        />
        {tools.length} tool{tools.length === 1 ? "" : "s"} used
        {seconds ? (
          <span className="ml-auto font-mono text-[10px] text-slate-400">
            {seconds.toFixed(1)}s
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {tools.map((tool, index) => (
            <span
              key={`${tool}-${index}`}
              className="rounded bg-slate-50 px-1.5 py-0.5 font-mono text-[9px] text-slate-600 ring-1 ring-slate-200"
            >
              {tool}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

interface Props {
  onBudgetDetected: (budgetUsd: number) => void;
  geminiModel: string | null;
  /** Text pushed in from elsewhere, e.g. the Action Plan's "Try Example"
   *  button. The nonce is what makes pressing it twice work: the text alone
   *  would be unchanged and the effect would not fire again. */
  prefill?: { text: string; nonce: number } | null;
}

export default function ChatPanel({
  onBudgetDetected,
  geminiModel,
  prefill,
}: Props) {
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement | null>(null);
  const composer = useRef<HTMLTextAreaElement | null>(null);

  // Generated after mount, never during render: a random id produced on the
  // server would not match the one produced in the browser, and React would
  // report a hydration mismatch.
  useEffect(() => {
    setSessionId(
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `session-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    );
  }, []);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (!prefill) return;
    setDraft(prefill.text);
    // Deliberately not sent. The official reads it, edits the figure if they
    // want, and presses Send themselves.
    composer.current?.focus();
  }, [prefill]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;

    setDraft("");
    setMessages((previous) => [
      ...previous,
      { id: `u${Date.now()}`, role: "user", text: question },
    ]);
    setBusy(true);

    const budget = parseBudget(question);
    const started = performance.now();

    try {
      const response = await sendChat(question, sessionId || "anonymous");
      const seconds = (performance.now() - started) / 1000;

      setMessages((previous) => [
        ...previous,
        {
          id: `a${Date.now()}`,
          role: "agent",
          text: response.reply,
          tools: response.tool_calls.map((call) => call.tool),
          seconds,
        },
      ]);

      // The agent decided this was a budget question; refresh the plan panel
      // with the same figure the official typed.
      if (budget && /budget|plan|invest|fund/i.test(response.reply)) {
        onBudgetDetected(budget);
      }
    } catch (exception) {
      setMessages((previous) => [
        ...previous,
        {
          id: `e${Date.now()}`,
          role: "error",
          text:
            exception instanceof Error ? exception.message : String(exception),
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex h-full flex-col bg-slate-50">
      <header className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-2.5 shadow-sm">
        <SparkIcon className="h-4 w-4 text-blue-800" />
        <h2 className="text-sm font-bold text-slate-800">Ask HeatGov AI</h2>
        {geminiModel ? (
          <span className="rounded-full bg-slate-200 px-2 py-0.5 font-mono text-[10px] text-slate-600">
            {geminiModel}
          </span>
        ) : null}
      </header>

      <div ref={scroller} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.length === 0 ? (
          <div className="space-y-2">
            <p className="text-xs text-slate-500">
              The agent queries the trained model directly. Every number it
              reports comes from a tool call, never from the language model.
            </p>
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => void send(suggestion)}
                className="block w-full rounded-xl bg-white px-3 py-2.5 text-left text-xs font-medium text-slate-700 shadow-sm ring-1 ring-slate-200 transition hover:-translate-y-px hover:text-blue-900 hover:shadow-md hover:ring-blue-300"
              >
                {suggestion}
              </button>
            ))}
          </div>
        ) : null}

        {messages.map((message) => {
          if (message.role === "user") {
            return (
              <div key={message.id} className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-br-md bg-blue-800 px-3.5 py-2 text-[13px] text-white shadow-md">
                  {message.text}
                </div>
              </div>
            );
          }
          if (message.role === "error") {
            return (
              <div
                key={message.id}
                className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-800 ring-1 ring-red-200"
              >
                <div className="font-semibold">Agent unavailable</div>
                <div className="mt-1 font-mono">{message.text}</div>
              </div>
            );
          }
          return (
            <div key={message.id} className="fade-up flex justify-start">
              <div className="max-w-[92%] rounded-2xl rounded-bl-md bg-white px-3.5 py-2.5 shadow-sm ring-1 ring-slate-200">
                <Markdown text={message.text} />
                {message.tools?.length ? (
                  <ToolTrace tools={message.tools} seconds={message.seconds} />
                ) : null}
              </div>
            </div>
          );
        })}

        {busy ? (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-blue-800" />
            HeatGov AI is thinking&hellip;
          </div>
        ) : null}
      </div>

      <div className="border-t border-slate-200 bg-white p-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={composer}
            data-tour="chat"
            value={draft}
            rows={2}
            disabled={busy}
            placeholder="Ask about heat risk or a budget..."
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends, Shift+Enter starts a new line.
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send(draft);
              }
            }}
            className="min-h-[44px] flex-1 resize-none rounded-xl border border-slate-300 px-3 py-2 text-[13px] text-slate-800 shadow-inner outline-none transition focus:border-blue-700 focus:ring-2 focus:ring-blue-700/30 disabled:bg-slate-50"
          />
          <button
            type="button"
            disabled={busy || !draft.trim()}
            onClick={() => void send(draft)}
            className="h-[44px] rounded-xl bg-blue-800 px-5 text-sm font-bold text-white shadow-md transition hover:bg-blue-900 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
          >
            Send
          </button>
        </div>
        <p className="mt-1 text-[10px] text-slate-400">
          Enter to send, Shift+Enter for a new line.
        </p>
      </div>
    </section>
  );
}
