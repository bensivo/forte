"""Tests for cost estimation module."""

from forte.services.agent._cost import PRICES, estimate_cost, format_cost_summary
from forte.services.agent._usage import Usage


class TestEstimateCost:
    """Tests for estimate_cost function."""

    def test_known_model_basic(self):
        """Test cost estimation for a known model with basic token usage."""
        model = "claude-haiku-4-5"
        usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)

        # Expected: 1M input * $1.00/1M + 1M output * $5.00/1M = $1.00 + $5.00
        expected = 1.00 + 5.00
        assert estimate_cost(model, usage) == expected

    def test_known_model_partial_tokens(self):
        """Test cost estimation with partial token counts."""
        model = "claude-sonnet-5"
        usage = Usage(input_tokens=500_000, output_tokens=250_000)

        # Expected: 500K input * $3.00/1M + 250K output * $15.00/1M
        # = 0.5 * 3.00 + 0.25 * 15.00 = 1.50 + 3.75 = 5.25
        expected = 0.5 * 3.00 + 0.25 * 15.00
        assert estimate_cost(model, usage) == expected

    def test_known_model_with_cache_tokens(self):
        """Test that cache tokens are treated as input tokens."""
        model = "claude-haiku-4-5"
        usage = Usage(
            input_tokens=500_000,
            output_tokens=500_000,
            cache_read_tokens=200_000,
            cache_creation_tokens=300_000,
        )

        # Total input-like tokens: 500K + 200K + 300K = 1M
        # Expected: 1M * $1.00/1M + 500K * $5.00/1M = $1.00 + $2.50 = $3.50
        expected = (1.0 * 1.00) + (0.5 * 5.00)
        assert estimate_cost(model, usage) == expected

    def test_unknown_model_returns_none(self):
        """Test that unknown models return None."""
        model = "claude-unknown-99"
        usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)

        assert estimate_cost(model, usage) is None

    def test_zero_tokens(self):
        """Test cost with zero tokens."""
        model = "claude-haiku-4-5"
        usage = Usage.zero()

        assert estimate_cost(model, usage) == 0.0

    def test_all_known_models_have_prices(self):
        """Verify that PRICES dict contains expected models."""
        expected_models = {"claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8"}
        assert expected_models.issubset(set(PRICES.keys()))

    def test_opus_pricing(self):
        """Test cost estimation for claude-opus-4-8."""
        model = "claude-opus-4-8"
        usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)

        # Expected: 1M input * $5.00/1M + 1M output * $25.00/1M = $5.00 + $25.00
        expected = 5.00 + 25.00
        assert estimate_cost(model, usage) == expected


class TestFormatCostSummary:
    """Tests for format_cost_summary function."""

    def test_known_model_contains_estimate_label(self):
        """Test that known model summary contains 'estimate' label."""
        model = "claude-haiku-4-5"
        usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)

        summary = format_cost_summary(model, usage)
        assert "estimate" in summary.lower()
        assert "$" in summary

    def test_known_model_contains_dollar_amount(self):
        """Test that known model summary contains a dollar amount."""
        model = "claude-sonnet-5"
        usage = Usage(input_tokens=100_000, output_tokens=50_000)

        summary = format_cost_summary(model, usage)
        assert "$" in summary
        # Should be able to extract a number like $0.XXXX
        assert "~$" in summary

    def test_unknown_model_no_crash(self):
        """Test that unknown model does not crash."""
        model = "claude-unknown-99"
        usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)

        # Should not raise
        summary = format_cost_summary(model, usage)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_unknown_model_omits_dollar_figure(self):
        """Test that unknown model omits cost but reports tokens."""
        model = "claude-unknown-99"
        usage = Usage(input_tokens=1_000_000, output_tokens=500_000)

        summary = format_cost_summary(model, usage)
        # Should not contain a dollar sign when model is unknown
        assert "$" not in summary
        # But should mention cost estimate unavailable
        assert "unavailable" in summary

    def test_format_contains_token_counts(self):
        """Test that format includes input/output/total token counts."""
        model = "claude-haiku-4-5"
        usage = Usage(input_tokens=100, output_tokens=50)

        summary = format_cost_summary(model, usage)
        assert "100" in summary  # input tokens
        assert "50" in summary  # output tokens
        assert "150" in summary  # total tokens

    def test_format_with_cache_tokens_shows_cache_line(self):
        """Test that format correctly includes cache tokens."""
        model = "claude-haiku-4-5"
        usage = Usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=30,
            cache_creation_tokens=20,
        )

        summary = format_cost_summary(model, usage)
        # Total cache = 30 + 20 = 50, so should show "cache: 50"
        assert "cache: 50" in summary
        # Total = 100 + 50 + 30 + 20 = 200
        assert "total: 200" in summary

    def test_format_with_zero_cache_tokens_no_cache_line(self):
        """Test that cache line is omitted when cache tokens are zero."""
        model = "claude-haiku-4-5"
        usage = Usage(input_tokens=100, output_tokens=50)

        summary = format_cost_summary(model, usage)
        # Should not show cache line when all cache tokens are 0
        assert "cache:" not in summary

    def test_format_is_single_line(self):
        """Test that format is approximately one line (no excessive output)."""
        model = "claude-sonnet-5"
        usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)

        summary = format_cost_summary(model, usage)
        # Should not have newlines
        assert "\n" not in summary

    def test_format_matches_example_pattern_known_model(self):
        """Test that format roughly matches the documented example."""
        model = "claude-haiku-4-5"
        usage = Usage(input_tokens=10, output_tokens=5)

        summary = format_cost_summary(model, usage)
        # Should contain all key parts
        assert "input:" in summary
        assert "output:" in summary
        assert "total:" in summary
        assert "tokens" in summary
        assert "~$" in summary
        assert "(estimated)" in summary

    def test_format_matches_example_pattern_unknown_model(self):
        """Test format for unknown model matches documented pattern."""
        model = "unknown-model"
        usage = Usage(input_tokens=10, output_tokens=5)

        summary = format_cost_summary(model, usage)
        # Should contain all key parts
        assert "input:" in summary
        assert "output:" in summary
        assert "total:" in summary
        assert "tokens" in summary
        assert "unavailable" in summary
        # Should contain the model name
        assert "unknown-model" in summary

    def test_cost_calculation_accuracy(self):
        """Test that cost in the summary string is calculated correctly."""
        model = "claude-haiku-4-5"
        usage = Usage(input_tokens=100_000, output_tokens=100_000)

        summary = format_cost_summary(model, usage)
        # Cost should be: 100K * 1.00/1M + 100K * 5.00/1M
        # = 0.1 * 1.00 + 0.1 * 5.00 = 0.1 + 0.5 = 0.6
        # So summary should contain ~$0.6000 or ~$0.60 (depending on formatting)
        assert "~$0.6" in summary
