"""Cost estimation for LLM API calls.

This module provides pricing information and cost estimation for Claude models.
The PRICES table below is the single place to update as model prices and
available models change.

Note: Cache tokens (both read and creation) are treated as regular input tokens
for cost estimation purposes. This provides a simpler, more conservative estimate
(cache reads are typically cheaper in real billing, but MVP costing is approximate).
"""

from __future__ import annotations

from forte.services.usage import Usage

# Per-1-MILLION-token pricing in USD: (input_price, output_price)
# Update this table as models and prices change.
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
}


def estimate_cost(model: str, usage: Usage) -> float | None:
    """Estimate the USD cost for an LLM call.

    Args:
        model: The model ID (e.g. "claude-haiku-4-5")
        usage: Token usage from the call, including input, output, and cache tokens

    Returns:
        Estimated USD cost, or None if the model is unknown (graceful degradation).

    Notes:
        Cache tokens (both read and creation) are treated as regular input tokens.
    """
    if model not in PRICES:
        return None

    input_price, output_price = PRICES[model]

    # Treat all input-like tokens as input tokens
    total_input = (
        usage.input_tokens + usage.cache_read_tokens + usage.cache_creation_tokens
    )

    # Cost = (tokens / 1,000,000) * price_per_million
    input_cost = (total_input / 1_000_000) * input_price
    output_cost = (usage.output_tokens / 1_000_000) * output_price

    return input_cost + output_cost


def format_cost_summary(model: str, usage: Usage) -> str:
    """Format a human-readable cost and token summary.

    Args:
        model: The model ID
        usage: Token usage from the run

    Returns:
        A concise one-line summary including token counts and estimated cost.
        For unknown models, reports tokens without a cost figure.

    Example:
        "input: 100, output: 50, total: 150 tokens (~$0.0005 (estimated))"
        "input: 100, output: 50, total: 150 tokens (cost estimate unavailable for
        model 'unknown-model')"
    """
    total_input = (
        usage.input_tokens + usage.cache_read_tokens + usage.cache_creation_tokens
    )
    total_tokens = total_input + usage.output_tokens

    cost = estimate_cost(model, usage)

    # Build the token summary part
    parts = [f"input: {usage.input_tokens}", f"output: {usage.output_tokens}"]

    # Add cache info if present
    total_cache = usage.cache_read_tokens + usage.cache_creation_tokens
    if total_cache > 0:
        parts.append(f"cache: {total_cache}")

    tokens_str = ", ".join(parts) + f", total: {total_tokens} tokens"

    if cost is not None:
        return f"{tokens_str} (~${cost:.4f} (estimated))"
    else:
        return (
            f"{tokens_str} "
            f"(cost estimate unavailable for model {model!r})"
        )
