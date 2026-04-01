"""
Live Assist Tab Test Suite
Tests the /live-assist/analyze endpoint, frontend HTML elements,
DEMO_CONFIG integration, tab switching, and edge cases.
All tests mock the model to avoid requiring Foundry Local.
"""

import os
import sys
import json
import re
import unittest

# Allow running from tests/ subdirectory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import patch, MagicMock

# Patch OpenAI before importing the app
mock_openai_client = MagicMock()
mock_openai_client.models.list.return_value = []

with patch.dict(os.environ, {}):
    with patch("openai.OpenAI", return_value=mock_openai_client):
        from io import StringIO
        _old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            import npu_demo_flask as app_module
        finally:
            sys.stdout = _old_stdout

app = app_module.app
app.config["TESTING"] = True


# =============================================================================
# Helpers
# =============================================================================

def mock_response(text, tokens=100):
    """Create a mock OpenAI chat completion response."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    resp.usage = MagicMock()
    resp.usage.total_tokens = tokens
    return resp


def set_mock_create(return_value):
    """Set mock on client.chat.completions.create. Returns old value for cleanup."""
    old = app_module.client.chat.completions.create
    app_module.client.chat.completions.create = MagicMock(return_value=return_value)
    return old


# =============================================================================
# DEMO_CONFIG Tests
# =============================================================================

class TestLiveAssistConfig(unittest.TestCase):
    """Verify Live Assist tab exists in DEMO_CONFIG."""

    def test_live_tab_in_demo_config(self):
        tabs = app_module.DEMO_CONFIG["tabs"]
        self.assertIn("live", tabs)

    def test_live_tab_has_required_keys(self):
        live = app_module.DEMO_CONFIG["tabs"]["live"]
        self.assertIn("name", live)
        self.assertIn("sub", live)
        self.assertIn("icon", live)

    def test_live_tab_name(self):
        self.assertEqual(app_module.DEMO_CONFIG["tabs"]["live"]["name"], "Live Assist")

    def test_live_tab_subtitle(self):
        self.assertEqual(app_module.DEMO_CONFIG["tabs"]["live"]["sub"], "Real-time Insights")


# =============================================================================
# Frontend HTML Tests
# =============================================================================

class TestLiveAssistHTML(unittest.TestCase):
    """Verify all Live Assist HTML elements are present in the rendered page."""

    @classmethod
    def setUpClass(cls):
        with app.test_client() as c:
            resp = c.get("/")
            cls.html = resp.data.decode("utf-8")

    def test_live_tab_content_div_exists(self):
        self.assertIn('id="live-tab"', self.html)

    def test_live_tab_has_tab_content_class(self):
        self.assertRegex(self.html, r'id="live-tab"\s+class="tab-content"')

    def test_transcript_pane_exists(self):
        self.assertIn('id="liveTranscriptPane"', self.html)

    def test_prompter_pane_exists(self):
        self.assertIn('id="livePrompterPane"', self.html)

    def test_transcript_area_exists(self):
        self.assertIn('id="liveTranscriptArea"', self.html)

    def test_insight_cards_container_exists(self):
        self.assertIn('id="liveInsightCards"', self.html)

    def test_voice_button_exists(self):
        self.assertIn('id="liveVoiceBtn"', self.html)

    def test_demo_button_exists(self):
        self.assertIn('id="liveDemoBtn"', self.html)

    def test_stop_button_exists(self):
        self.assertIn('id="liveStopBtn"', self.html)

    def test_status_text_exists(self):
        self.assertIn('id="liveStatusText"', self.html)

    def test_pulse_dot_exists(self):
        self.assertIn('id="livePulseDot"', self.html)

    def test_insight_dot_exists(self):
        self.assertIn('id="liveInsightDot"', self.html)

    def test_live_btn_class(self):
        self.assertIn('class="live-btn"', self.html)

    def test_voice_button_label(self):
        self.assertIn("Start Live Voice", self.html)

    def test_demo_button_label(self):
        self.assertIn("Run Demo Script", self.html)


# =============================================================================
# Sidebar Navigation Tests
# =============================================================================

class TestLiveAssistSidebar(unittest.TestCase):
    """Verify sidebar nav item renders correctly."""

    @classmethod
    def setUpClass(cls):
        with app.test_client() as c:
            resp = c.get("/")
            cls.html = resp.data.decode("utf-8")

    def test_sidebar_nav_item_exists(self):
        self.assertIn('data-tab="live"', self.html)

    def test_sidebar_shows_tab_name(self):
        self.assertIn("Live Assist", self.html)

    def test_sidebar_shows_tab_subtitle(self):
        self.assertIn("Real-time Insights", self.html)

    def test_hidden_tab_button_exists(self):
        self.assertIn('id="liveTabBtn"', self.html)

    def test_tab_button_in_tabs_div(self):
        # liveTabBtn should be inside the hidden .tabs div
        match = re.search(r'class="tabs"[^>]*>.*?</div>', self.html, re.DOTALL)
        self.assertIsNotNone(match)
        self.assertIn("liveTabBtn", match.group(0))


# =============================================================================
# Tab Switching JavaScript Tests
# =============================================================================

class TestLiveAssistTabSwitching(unittest.TestCase):
    """Verify tab switching JS is wired up."""

    @classmethod
    def setUpClass(cls):
        with app.test_client() as c:
            resp = c.get("/")
            cls.html = resp.data.decode("utf-8")

    def test_tabmap_has_live_entry(self):
        self.assertIn('"live-tab"', self.html)
        self.assertIn('"liveTabBtn"', self.html)

    def test_tab_toast_message(self):
        self.assertIn("real-time meeting insights", self.html)

    def test_live_tab_btn_event_listener(self):
        self.assertIn('getElementById("liveTabBtn")', self.html)


# =============================================================================
# CSS Tests
# =============================================================================

class TestLiveAssistCSS(unittest.TestCase):
    """Verify Live Assist CSS styles are present."""

    @classmethod
    def setUpClass(cls):
        with app.test_client() as c:
            resp = c.get("/")
            cls.html = resp.data.decode("utf-8")

    def test_layout_class(self):
        self.assertIn(".live-assist-layout", self.html)

    def test_transcript_pane_class(self):
        self.assertIn(".live-transcript-pane", self.html)

    def test_prompter_pane_class(self):
        self.assertIn(".live-prompter-pane", self.html)

    def test_bottom_bar_class(self):
        self.assertIn(".live-bottom-bar", self.html)

    def test_insight_card_class(self):
        self.assertIn(".live-insight-card", self.html)

    def test_sentiment_classes(self):
        self.assertIn(".sentiment-positive", self.html)
        self.assertIn(".sentiment-neutral", self.html)
        self.assertIn(".sentiment-cautious", self.html)

    def test_pulse_animation(self):
        self.assertIn("@keyframes livePulse", self.html)

    def test_fade_animation(self):
        self.assertIn("@keyframes liveFadeIn", self.html)

    def test_grid_layout_60_40(self):
        # Should be 3fr 2fr (60/40 split)
        self.assertIn("3fr 2fr", self.html)


# =============================================================================
# /live-assist/analyze Endpoint Tests
# =============================================================================

class TestLiveAssistAnalyze(unittest.TestCase):
    """Test the /live-assist/analyze endpoint."""

    def setUp(self):
        self.client = app.test_client()

    def test_analyze_returns_json(self):
        model_text = "Customer is interested in savings. Consider recommending high-yield account.\nSENTIMENT: POSITIVE"
        old = set_mock_create(mock_response(model_text, tokens=85))
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "I need to set up checking and savings.",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("insights", data)
        self.assertIn("sentiment", data)
        self.assertIn("tokens_used", data)

    def test_analyze_positive_sentiment(self):
        model_text = "Customer sounds enthusiastic about opening accounts.\nSENTIMENT: POSITIVE"
        old = set_mock_create(mock_response(model_text))
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "Let's go ahead and get the checking set up today.",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        data = json.loads(resp.data)
        self.assertEqual(data["sentiment"], "POSITIVE")

    def test_analyze_cautious_sentiment(self):
        model_text = "Customer is concerned about fees. Address fee transparency.\nSENTIMENT: CAUTIOUS"
        old = set_mock_create(mock_response(model_text))
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "The fees at my last bank were ridiculous.",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        data = json.loads(resp.data)
        self.assertEqual(data["sentiment"], "CAUTIOUS")

    def test_analyze_neutral_sentiment(self):
        model_text = "Customer is asking factual questions about accounts.\nSENTIMENT: NEUTRAL"
        old = set_mock_create(mock_response(model_text))
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "What are the monthly fees on your checking accounts?",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        data = json.loads(resp.data)
        self.assertEqual(data["sentiment"], "NEUTRAL")

    def test_analyze_strips_sentiment_line_from_insights(self):
        model_text = "Customer mentioned two children. Recommend 529 plan.\nSENTIMENT: POSITIVE"
        old = set_mock_create(mock_response(model_text))
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "I have two kids, Maya is eight and Daniel is fifteen.",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        data = json.loads(resp.data)
        # insights should NOT contain "SENTIMENT: POSITIVE" line
        self.assertNotIn("SENTIMENT:", data["insights"])
        self.assertIn("529 plan", data["insights"])

    def test_analyze_with_prior_insights(self):
        model_text = "Customer is behind on retirement. Suggest IRA options.\nSENTIMENT: CAUTIOUS"
        old = set_mock_create(mock_response(model_text))
        mock_ref = app_module.client.chat.completions.create
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "I'm forty-five, so I feel like I'm behind on retirement planning.",
                "prior": "Customer mentioned two children | Recommend 529 plan"
            })
        finally:
            app_module.client.chat.completions.create = old

        self.assertEqual(resp.status_code, 200)
        call_kwargs = mock_ref.call_args.kwargs
        system_msg = call_kwargs["messages"][0]["content"]
        self.assertIn("529 plan", system_msg)

    def test_analyze_returns_tokens_used(self):
        model_text = "Consider recommending college savings.\nSENTIMENT: POSITIVE"
        old = set_mock_create(mock_response(model_text, tokens=150))
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "We've been talking about saving for their college.",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        data = json.loads(resp.data)
        self.assertEqual(data["tokens_used"], 150)

    def test_analyze_returns_inference_time(self):
        model_text = "General inquiry.\nSENTIMENT: NEUTRAL"
        old = set_mock_create(mock_response(model_text))
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "Hello, I'm looking for information.",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        data = json.loads(resp.data)
        self.assertIn("inference_time", data)
        self.assertIsInstance(data["inference_time"], float)

    def test_analyze_empty_text_returns_400(self):
        resp = self.client.post("/live-assist/analyze", json={
            "text": "",
            "prior": ""
        })
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertIn("error", data)

    def test_analyze_whitespace_only_returns_400(self):
        resp = self.client.post("/live-assist/analyze", json={
            "text": "   \n  ",
            "prior": ""
        })
        self.assertEqual(resp.status_code, 400)

    def test_analyze_missing_text_field_returns_400(self):
        resp = self.client.post("/live-assist/analyze", json={
            "prior": "something"
        })
        self.assertEqual(resp.status_code, 400)

    def test_analyze_no_json_body(self):
        resp = self.client.post("/live-assist/analyze",
                                data="not json",
                                content_type="text/plain")
        # Should return error (400 or 500)
        self.assertIn(resp.status_code, [400, 415, 500])

    def test_analyze_default_sentiment_is_neutral(self):
        """If model output doesn't contain a sentiment keyword, default to NEUTRAL."""
        model_text = "Customer wants to open checking account."
        old = set_mock_create(mock_response(model_text))
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "I need a checking account.",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        data = json.loads(resp.data)
        self.assertEqual(data["sentiment"], "NEUTRAL")

    def test_analyze_model_error_returns_500(self):
        old = app_module.client.chat.completions.create
        app_module.client.chat.completions.create = MagicMock(
            side_effect=Exception("Model offline")
        )
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "Hello",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        self.assertEqual(resp.status_code, 500)
        data = json.loads(resp.data)
        self.assertIn("error", data)
        self.assertIn("Model offline", data["error"])

    def test_analyze_long_transcript_chunk(self):
        """Ensure long transcript chunks are handled without error."""
        long_text = "Customer is talking about finances. " * 50
        model_text = "Multiple topics discussed.\nSENTIMENT: NEUTRAL"
        old = set_mock_create(mock_response(model_text))
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": long_text,
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        self.assertEqual(resp.status_code, 200)

    def test_analyze_uses_correct_model(self):
        """Verify the endpoint uses DEFAULT_MODEL."""
        model_text = "Test.\nSENTIMENT: NEUTRAL"
        old = set_mock_create(mock_response(model_text))
        mock_ref = app_module.client.chat.completions.create
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "Test input.",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        call_kwargs = mock_ref.call_args.kwargs
        self.assertEqual(call_kwargs["model"], app_module.DEFAULT_MODEL)

    def test_analyze_max_tokens_128(self):
        """Verify max_tokens is set to 128 for concise bullet responses."""
        model_text = "Test.\nSENTIMENT: NEUTRAL"
        old = set_mock_create(mock_response(model_text))
        mock_ref = app_module.client.chat.completions.create
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "Test input.",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        call_kwargs = mock_ref.call_args.kwargs
        self.assertEqual(call_kwargs["max_tokens"], 128)

    def test_analyze_temperature_03(self):
        """Verify temperature is set to 0.3 for consistent insights."""
        model_text = "Test.\nSENTIMENT: NEUTRAL"
        old = set_mock_create(mock_response(model_text))
        mock_ref = app_module.client.chat.completions.create
        try:
            resp = self.client.post("/live-assist/analyze", json={
                "text": "Test input.",
                "prior": ""
            })
        finally:
            app_module.client.chat.completions.create = old

        call_kwargs = mock_ref.call_args.kwargs
        self.assertAlmostEqual(call_kwargs["temperature"], 0.3)


# =============================================================================
# JavaScript Presence Tests
# =============================================================================

class TestLiveAssistJavaScript(unittest.TestCase):
    """Verify key JS logic is present in the rendered page."""

    @classmethod
    def setUpClass(cls):
        with app.test_client() as c:
            resp = c.get("/")
            cls.html = resp.data.decode("utf-8")

    def test_speech_recognition_api_reference(self):
        self.assertIn("SpeechRecognition", self.html)

    def test_webkit_speech_recognition_fallback(self):
        self.assertIn("webkitSpeechRecognition", self.html)

    def test_continuous_recognition_enabled(self):
        self.assertIn("recognition.continuous = true", self.html)

    def test_interim_results_enabled(self):
        self.assertIn("recognition.interimResults = true", self.html)

    def test_demo_script_array_exists(self):
        self.assertIn("_liveAssistDemoScript", self.html)

    def test_demo_script_has_lines(self):
        # Should have the Jackie Rodriguez conversation
        self.assertIn("Jackie", self.html)
        self.assertIn("529 plan", self.html)

    def test_analysis_fetch_call(self):
        self.assertIn("/live-assist/analyze", self.html)

    def test_interim_class_for_partial_speech(self):
        self.assertIn("interim", self.html)

    def test_session_summary_at_end(self):
        self.assertIn("Session Complete", self.html)

    def test_auto_restart_on_silence(self):
        # Voice recognition should auto-restart when browser stops on silence
        self.assertIn('_liveMode === "voice"', self.html)

    def test_buffering_logic_exists(self):
        self.assertIn("_liveSentIndex", self.html)
        self.assertIn("checkAnalysisTrigger", self.html)

    def test_max_one_inflight_analysis(self):
        self.assertIn("_liveAnalyzing", self.html)

    def test_prior_insights_dedup(self):
        self.assertIn("_livePriorInsights", self.html)


# =============================================================================
# Template Variable Tests
# =============================================================================

class TestLiveAssistTemplateVars(unittest.TestCase):
    """Verify no unresolved template variables in rendered page."""

    @classmethod
    def setUpClass(cls):
        with app.test_client() as c:
            resp = c.get("/")
            cls.html = resp.data.decode("utf-8")

    def test_no_unresolved_live_template_vars(self):
        self.assertNotIn("{{TAB_LIVE_NAME}}", self.html)
        self.assertNotIn("{{TAB_LIVE_SUB}}", self.html)
        self.assertNotIn("{{TAB_LIVE_ICON}}", self.html)


# =============================================================================
# Integration: Tab Order
# =============================================================================

class TestLiveAssistTabOrder(unittest.TestCase):
    """Verify Live Assist tab appears between ID Verification and Field Inspection."""

    @classmethod
    def setUpClass(cls):
        with app.test_client() as c:
            resp = c.get("/")
            cls.html = resp.data.decode("utf-8")

    def test_sidebar_order_id_before_live(self):
        id_pos = self.html.find('data-tab="id"')
        live_pos = self.html.find('data-tab="live"')
        self.assertGreater(live_pos, id_pos)

    def test_sidebar_order_live_before_field(self):
        live_pos = self.html.find('data-tab="live"')
        field_pos = self.html.find('data-tab="field"')
        self.assertGreater(field_pos, live_pos)

    def test_tab_content_order_id_before_live(self):
        id_pos = self.html.find('id="id-tab"')
        live_pos = self.html.find('id="live-tab"')
        self.assertGreater(live_pos, id_pos)

    def test_tab_content_order_live_before_field(self):
        live_pos = self.html.find('id="live-tab"')
        field_pos = self.html.find('id="field-tab"')
        self.assertGreater(field_pos, live_pos)

    def test_hidden_btn_order(self):
        id_pos = self.html.find('id="idTabBtn"')
        live_pos = self.html.find('id="liveTabBtn"')
        field_pos = self.html.find('id="fieldTabBtn"')
        self.assertGreater(live_pos, id_pos)
        self.assertGreater(field_pos, live_pos)


if __name__ == "__main__":
    unittest.main()
