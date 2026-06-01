import json
import logging
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from app.config import settings
from app.services.chat_tools import TOOL_DEFINITIONS, TOOL_LABELS, execute_tool

logger = logging.getLogger("chat")

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
MAX_TOOL_ITERATIONS = 5

SYSTEM_PROMPT = """You are a thoughtful, plain-language personal finance advisor for the user. Your goal is to help them make better decisions about money — budgeting, saving, debt, investing, retirement, taxes, and major purchases.

Style:
- Conversational and warm, never patronizing.
- Concrete: give specific numbers, ranges, or recommendations whenever you have enough info.
- Ask clarifying questions when the answer truly depends on info you don't have. Don't ask more than two at a time.
- Use short paragraphs, lists, and tables when they help comprehension.

Substance:
- Reason from first principles, not generic platitudes.
- When the user has shared their situation, factor it into every relevant answer.
- Be explicit about tradeoffs (e.g., "capture the 401k match first, then pay down 7% loans before maxing the Roth").
- For investing, default to broad-market index funds, target-date funds, and tax-advantaged accounts. Don't make specific buy/sell calls on individual securities.

Using your tools:
- You have tools to read the user's actual portfolio and individual holdings. When the user asks about how their portfolio is doing, their positions, allocation, returns, or any specific security they own, CALL the relevant tool first instead of asking them to share what's already in the system.
- Prefer `get_portfolio_summary` for high-level questions ("how am I doing?", "what's my biggest position?", "how much am I up?"). Use `list_holdings` when you need the full per-position detail or a security type that may not appear in the summary's top 10.
- After getting tool results, weave the actual numbers into your answer naturally — don't dump the raw data.
- If a tool returns an empty portfolio, gently invite them to add holdings on the Portfolio page.

Boundaries (be clear, not preachy):
- You are not a licensed financial advisor, tax professional, or attorney. For binding decisions (filing taxes, signing legal docs, complex estate planning), recommend a qualified professional.
- For specific tax filing questions, point them to a CPA or tax software.
- If asked about specific securities (stocks, options, crypto), explain general considerations but don't recommend buy/sell.

When the user has shared context about their finances below, treat it as authoritative and reason from it. If a question depends on info they haven't shared, ask."""


_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def build_system_blocks(financial_context: str | None) -> list[dict]:
    blocks = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
    ]
    if financial_context and financial_context.strip():
        blocks.append({
            "type": "text",
            "text": f"<user_financial_context>\n{financial_context.strip()}\n</user_financial_context>",
            "cache_control": {"type": "ephemeral"},
        })
    return blocks


def build_messages(prior: list[dict], user_content: str) -> list[dict]:
    messages = []
    for m in prior:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_content})
    return messages


def _to_content_param(block) -> dict:
    """Convert an SDK response content block back into an API-valid content param
    for replay. model_dump() leaks SDK-only fields (e.g. text blocks now carry
    `parsed_output`) that the Messages API rejects as 'extra inputs', so map the
    block types we use explicitly and strip extras on the fallback."""
    btype = getattr(block, "type", None)
    if btype == "text":
        return {"type": "text", "text": block.text}
    if btype == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    data = block.model_dump()
    data.pop("parsed_output", None)
    return data


async def stream_chat(
    user_id: str,
    prior_messages: list[dict],
    user_content: str,
    financial_context: str | None,
) -> AsyncIterator[dict]:
    """Yields events:
      - {'type': 'text', 'text': str} for each streamed text delta
      - {'type': 'tool_use_start', 'id': str, 'tool': str, 'label': str}
      - {'type': 'tool_use_done', 'id': str, 'tool': str}
      - {'type': 'done', 'content': str, 'model': str, ...usage..., 'tool_calls': list}
    Raises on API errors."""
    client = get_client()
    system_blocks = build_system_blocks(financial_context)
    messages = build_messages(prior_messages, user_content)

    full_text = ""
    tool_calls_record: list[dict] = []
    total_input = 0
    total_output = 0
    total_cached = 0
    last_model = MODEL
    stop_reason = "end_turn"

    for iteration in range(MAX_TOOL_ITERATIONS + 1):
        async with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_blocks,
            messages=messages,
            tools=TOOL_DEFINITIONS,
        ) as stream:
            async for text in stream.text_stream:
                full_text += text
                yield {"type": "text", "text": text}
            final = await stream.get_final_message()

        usage = final.usage
        total_input += getattr(usage, "input_tokens", 0) or 0
        total_output += getattr(usage, "output_tokens", 0) or 0
        total_cached += getattr(usage, "cache_read_input_tokens", 0) or 0
        last_model = final.model
        stop_reason = final.stop_reason

        if stop_reason != "tool_use":
            break

        if iteration == MAX_TOOL_ITERATIONS:
            msg = "\n\n(Stopped: reached the tool-call limit.)"
            full_text += msg
            yield {"type": "text", "text": msg}
            break

        # Replay the assistant turn (text + tool_use blocks) before responding with tool_results.
        messages.append({
            "role": "assistant",
            "content": [_to_content_param(block) for block in final.content],
        })

        tool_results: list[dict] = []
        for block in final.content:
            if block.type != "tool_use":
                continue
            tool_input = dict(block.input or {})
            label = TOOL_LABELS.get(block.name, f"Running {block.name}…")
            yield {
                "type": "tool_use_start",
                "id": block.id,
                "tool": block.name,
                "label": label,
            }
            result = await execute_tool(user_id, block.name, tool_input)
            tool_calls_record.append({
                "id": block.id,
                "name": block.name,
                "input": tool_input,
                "result": result,
            })
            yield {"type": "tool_use_done", "id": block.id, "tool": block.name}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

    yield {
        "type": "done",
        "content": full_text,
        "model": last_model,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cached_input_tokens": total_cached,
        "tool_calls": tool_calls_record,
    }
