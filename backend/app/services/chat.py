import logging
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from app.config import settings

logger = logging.getLogger("chat")

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048

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


async def stream_chat(
    prior_messages: list[dict],
    user_content: str,
    financial_context: str | None,
) -> AsyncIterator[dict]:
    """Yields events: {'type': 'text', 'text': str} during streaming,
    and a single {'type': 'done', 'content': str, 'model': str,
    'input_tokens': int, 'output_tokens': int, 'cached_input_tokens': int}
    at the end. Raises on API errors."""
    client = get_client()
    system_blocks = build_system_blocks(financial_context)
    messages = build_messages(prior_messages, user_content)

    full_text = ""
    async with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_blocks,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            full_text += text
            yield {"type": "text", "text": text}
        final = await stream.get_final_message()

    usage = final.usage
    yield {
        "type": "done",
        "content": full_text,
        "model": final.model,
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cached_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
    }
