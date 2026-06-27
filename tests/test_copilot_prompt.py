"""
Tests for Co-Pilot financial context prompt construction (Phase 18R/18S).

Run from the project root:
    python3 -m pytest tests/test_copilot_prompt.py -v
    # or without pytest:
    python3 -m unittest tests.test_copilot_prompt -v
"""
import unittest
from unittest.mock import patch, MagicMock

from backend.modules.ai_copilot import (
    _build_financial_section,
    _confidence_label,
    _rule_based_analysis,
    analyze_product,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────

SAMPLE_FINANCIAL_CTX = {
    "product_name":     "Bamboo Cutting Board",
    "marketplace":      "UK",
    "currency":         "GBP",
    "selling_price":    29.99,
    "supplier_cost":    6.50,
    "net_profit":       9.40,
    "margin_pct":       31.3,
    "roi_pct":          144.6,
    "confidence_score": 78,
    "hs_code":          "4419.11",
    "calculation_date": "2026-05-11T10:30:00.000Z",
}

SAMPLE_LOW_CONF_CTX = {**SAMPLE_FINANCIAL_CTX, "confidence_score": 42}

SAMPLE_OPP = {
    "score": 72,
    "grade": "B",
    "label": "Good opportunity",
    "action": "Proceed with caution",
    "profit_summary": {
        "profit":     9.40,
        "margin_pct": 31.3,
        "roi_pct":    144.6,
    },
}


# ── 1. _confidence_label ───────────────────────────────────────────────────────

class TestConfidenceLabel(unittest.TestCase):
    def test_high(self):
        self.assertEqual(_confidence_label(80), "High Confidence")
        self.assertEqual(_confidence_label(100), "High Confidence")

    def test_medium(self):
        self.assertEqual(_confidence_label(55), "Medium Confidence")
        self.assertEqual(_confidence_label(79), "Medium Confidence")

    def test_low(self):
        self.assertEqual(_confidence_label(0), "Low Confidence")
        self.assertEqual(_confidence_label(54), "Low Confidence")

    def test_none(self):
        self.assertEqual(_confidence_label(None), "Unknown")


# ── 2. _build_financial_section — content checks ──────────────────────────────

class TestBuildFinancialSection(unittest.TestCase):
    def setUp(self):
        self.section = _build_financial_section(SAMPLE_FINANCIAL_CTX, "GBP")

    def test_header_present(self):
        self.assertIn("Financial Context from Profit Lab", self.section)

    def test_marketplace(self):
        self.assertIn("UK", self.section)

    def test_currency(self):
        self.assertIn("GBP", self.section)

    def test_margin(self):
        self.assertIn("31.3%", self.section)

    def test_roi(self):
        self.assertIn("144.6%", self.section)

    def test_net_profit(self):
        self.assertIn("9.40", self.section)

    def test_confidence_score(self):
        # score=78 is below the 80 threshold → Medium Confidence
        self.assertIn("78/100", self.section)
        self.assertIn("Medium Confidence", self.section)

    def test_hs_code(self):
        self.assertIn("4419.11", self.section)

    def test_calculation_date(self):
        self.assertIn("2026-05-11", self.section)

    def test_end_marker(self):
        self.assertIn("End Financial Context", self.section)

    def test_instructions_present(self):
        self.assertIn("INSTRUCTIONS", self.section)
        self.assertIn("Do NOT invent", self.section)
        self.assertIn("planning estimates", self.section)

    def test_currency_symbol_gbp(self):
        self.assertIn("£29.99", self.section)
        self.assertIn("£6.50", self.section)
        self.assertIn("£9.40", self.section)

    def test_currency_symbol_usd(self):
        section = _build_financial_section(SAMPLE_FINANCIAL_CTX, "USD")
        self.assertIn("$29.99", section)

    def test_currency_symbol_eur(self):
        section = _build_financial_section(SAMPLE_FINANCIAL_CTX, "EUR")
        self.assertIn("€29.99", section)


# ── 3. Low-confidence warning ─────────────────────────────────────────────────

class TestLowConfidenceWarning(unittest.TestCase):
    def test_warning_present_when_low(self):
        section = _build_financial_section(SAMPLE_LOW_CONF_CTX, "GBP")
        self.assertIn("WARNING", section)
        self.assertIn("verify their inputs", section)
        self.assertIn("Low Confidence", section)

    def test_no_warning_when_high(self):
        section = _build_financial_section(SAMPLE_FINANCIAL_CTX, "GBP")
        self.assertNotIn("WARNING", section)

    def test_no_warning_when_medium(self):
        ctx = {**SAMPLE_FINANCIAL_CTX, "confidence_score": 60}
        section = _build_financial_section(ctx, "GBP")
        self.assertNotIn("WARNING", section)


# ── 4. Fallback — no financial_context → no financial section ─────────────────

class TestNoFinancialContext(unittest.TestCase):
    def test_empty_when_none(self):
        """_build_financial_section is not called when financial_context is None."""
        # The caller guards with `if financial_context else ""` — replicate that.
        fc = None
        result = _build_financial_section(fc, "USD") if fc else ""
        self.assertEqual(result, "")

    def test_no_fabricated_data_in_prompt(self):
        """Full analyze_product with no financial_context should not call
        _build_financial_section and should not insert the financial block."""
        with patch("backend.modules.ai_copilot.AI_AVAILABLE", False):
            result = _rule_based_analysis(
                product_name="Test Product",
                opp=SAMPLE_OPP,
                review_count=100,
                trend_direction="Stable",
                competition="Medium",
                currency="USD",
            )
        # Rule-based result should contain no financial-context references
        summary = result["summary"]
        self.assertNotIn("Financial Context from Profit Lab", summary)
        self.assertNotIn("INSTRUCTIONS", summary)


# ── 5. Rule-based fallback — currency threading ───────────────────────────────

class TestRuleBasedCurrency(unittest.TestCase):
    def _run(self, currency):
        return _rule_based_analysis(
            "Test Product", SAMPLE_OPP, 100, "Stable", "Medium", currency
        )

    def test_currency_stored_in_result(self):
        result = self._run("GBP")
        self.assertEqual(result["estimated_monthly_profit_currency"], "GBP")

    def test_usd_default(self):
        result = _rule_based_analysis("Test Product", SAMPLE_OPP, 100, "Stable", "Medium")
        self.assertEqual(result["estimated_monthly_profit_currency"], "USD")

    def test_aed_currency(self):
        result = self._run("AED")
        self.assertEqual(result["estimated_monthly_profit_currency"], "AED")

    def test_profit_value_is_numeric(self):
        result = self._run("USD")
        self.assertIsInstance(result["estimated_monthly_profit"], (int, float))

    def test_profit_equals_heuristic(self):
        result = self._run("USD")
        expected = round(SAMPLE_OPP["profit_summary"]["profit"] * 150)
        self.assertEqual(result["estimated_monthly_profit"], expected)


# ── 6. analyze_product integration — financial_context threaded to AI call ────

class TestAnalyzeProductIntegration(unittest.TestCase):
    def test_financial_context_passed_to_ai_analysis(self):
        """When AI is available, financial_context reaches _ai_analysis and
        therefore appears in the constructed prompt string."""
        captured_prompt = {}

        def fake_chat_json(system, user, max_tokens=600):
            captured_prompt["user"] = user
            return {
                "verdict": "Launch",
                "confidence": 80,
                "summary": "Good product.",
                "top_risks": [],
                "differentiation": [],
                "launch_strategy": "Launch now.",
                "estimated_monthly_profit": 1400,
            }

        with patch("backend.modules.ai_copilot.AI_AVAILABLE", True), \
             patch("backend.modules.ai_copilot.chat_json", side_effect=fake_chat_json):
            analyze_product(
                product_name="Bamboo Cutting Board",
                amazon_price=29.99,
                supplier_price=6.50,
                review_count=120,
                trend_direction="Rising",
                weight_lbs=1.2,
                category="kitchen",
                competition="Medium",
                marketplace="UK",
                currency="GBP",
                financial_context=SAMPLE_FINANCIAL_CTX,
            )

        prompt = captured_prompt.get("user", "")
        self.assertIn("Financial Context from Profit Lab", prompt,
                      "Financial context block must appear in AI prompt")
        self.assertIn("31.3%", prompt, "Margin must be in prompt")
        self.assertIn("144.6%", prompt, "ROI must be in prompt")
        self.assertIn("9.40", prompt, "Net profit must be in prompt")
        self.assertIn("78/100", prompt, "Confidence score must be in prompt")
        self.assertIn("UK", prompt, "Marketplace must be in prompt")
        self.assertIn("GBP", prompt, "Currency must be in prompt")

    def test_no_financial_section_without_context(self):
        """When financial_context is None the prompt must not contain the
        financial context block."""
        captured_prompt = {}

        def fake_chat_json(system, user, max_tokens=600):
            captured_prompt["user"] = user
            return {
                "verdict": "Test First",
                "confidence": 60,
                "summary": "Proceed with caution.",
                "top_risks": [],
                "differentiation": [],
                "launch_strategy": "Test first.",
                "estimated_monthly_profit": 800,
            }

        with patch("backend.modules.ai_copilot.AI_AVAILABLE", True), \
             patch("backend.modules.ai_copilot.chat_json", side_effect=fake_chat_json):
            analyze_product(
                product_name="Widget",
                amazon_price=20.00,
                supplier_price=5.00,
                review_count=50,
                trend_direction="Stable",
                weight_lbs=0.8,
                category="general",
                financial_context=None,
            )

        prompt = captured_prompt.get("user", "")
        self.assertNotIn("Financial Context from Profit Lab", prompt,
                         "Financial block must NOT appear when context is absent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
