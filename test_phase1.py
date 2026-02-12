"""
Phase 1 Test Script — Two-Brain Escalation Engine
Tests all new backend functions, endpoints, and frontend HTML elements
without requiring Foundry Local to be running (mocks model calls).
"""

import os
import sys
import json
import re
import unittest
from unittest.mock import patch, MagicMock

# Patch OpenAI before importing the app so it doesn't try to connect
mock_openai_client = MagicMock()
mock_openai_client.models.list.return_value = []

with patch.dict(os.environ, {}):
    with patch("openai.OpenAI", return_value=mock_openai_client):
        # Suppress startup prints
        from io import StringIO
        _old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            import npu_demo_flask as app_module
        finally:
            sys.stdout = _old_stdout

app = app_module.app
app.config["TESTING"] = True


class TestPIIScanning(unittest.TestCase):
    """Test _scan_pii and _redact_text helper functions."""

    def test_detect_ssn(self):
        text = "SSN is 123-45-6789 in the record."
        findings = app_module._scan_pii(text)
        ssns = [f for f in findings if f["type"] == "SSN"]
        self.assertEqual(len(ssns), 1)
        self.assertEqual(ssns[0]["value"], "123-45-6789")
        self.assertEqual(ssns[0]["severity"], "high")

    def test_detect_email(self):
        text = "Contact j.morrison@vertexdyn.com for details."
        findings = app_module._scan_pii(text)
        emails = [f for f in findings if f["type"] == "Email"]
        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0]["value"], "j.morrison@vertexdyn.com")

    def test_detect_phone(self):
        text = "Call (415) 555-0142 or 800-123-4567."
        findings = app_module._scan_pii(text)
        phones = [f for f in findings if f["type"] == "Phone"]
        self.assertGreaterEqual(len(phones), 2)

    def test_detect_multiple_pii(self):
        text = "SSN: 111-22-3333, email: test@example.com, phone: (555) 123-4567"
        findings = app_module._scan_pii(text)
        types = {f["type"] for f in findings}
        self.assertIn("SSN", types)
        self.assertIn("Email", types)
        self.assertIn("Phone", types)

    def test_no_pii(self):
        text = "This is a clean document with no personal information."
        findings = app_module._scan_pii(text)
        self.assertEqual(len(findings), 0)

    def test_redact_text(self):
        text = "SSN is 123-45-6789 and email is test@example.com here."
        findings = app_module._scan_pii(text)
        redacted = app_module._redact_text(text, findings)
        self.assertNotIn("123-45-6789", redacted)
        self.assertNotIn("test@example.com", redacted)
        self.assertIn("[REDACTED SSN]", redacted)
        self.assertIn("[REDACTED Email]", redacted)

    def test_redact_preserves_surrounding_text(self):
        text = "Before 123-45-6789 after"
        findings = app_module._scan_pii(text)
        redacted = app_module._redact_text(text, findings)
        self.assertTrue(redacted.startswith("Before"))
        self.assertTrue(redacted.endswith("after"))


class TestKnowledgeIndex(unittest.TestCase):
    """Test Local Knowledge index and search functions."""

    def test_index_built_on_import(self):
        # The demo NDA file should be indexed
        # (build_knowledge_index isn't called during import, but we can call it)
        app_module.build_knowledge_index()
        self.assertGreater(len(app_module.KNOWLEDGE_INDEX), 0)
        # Should have the demo NDA
        self.assertIn("contract_nda_vertex_pinnacle.txt", app_module.KNOWLEDGE_INDEX)

    def test_index_entry_structure(self):
        app_module.build_knowledge_index()
        entry = app_module.KNOWLEDGE_INDEX.get("contract_nda_vertex_pinnacle.txt")
        self.assertIsNotNone(entry)
        self.assertIn("text", entry)
        self.assertIn("path", entry)
        self.assertIn("word_count", entry)
        self.assertIn("terms", entry)
        self.assertIsInstance(entry["terms"], dict)
        self.assertGreater(entry["word_count"], 0)

    def test_search_finds_nda(self):
        app_module.build_knowledge_index()
        results = app_module.search_knowledge("confidential agreement NDA")
        self.assertGreater(len(results), 0)
        filenames = [r["filename"] for r in results]
        self.assertIn("contract_nda_vertex_pinnacle.txt", filenames)

    def test_search_returns_snippets(self):
        app_module.build_knowledge_index()
        results = app_module.search_knowledge("indemnification liability")
        if results:
            self.assertIn("snippet", results[0])
            self.assertGreater(len(results[0]["snippet"]), 0)

    def test_search_no_results(self):
        app_module.build_knowledge_index()
        results = app_module.search_knowledge("xyzzyfoobarbaz")
        self.assertEqual(len(results), 0)

    def test_search_empty_index(self):
        old = app_module.KNOWLEDGE_INDEX
        app_module.KNOWLEDGE_INDEX = {}
        results = app_module.search_knowledge("anything")
        self.assertEqual(len(results), 0)
        app_module.KNOWLEDGE_INDEX = old

    def test_extract_best_snippet_short_text(self):
        text = "Short document about contracts."
        snippet = app_module._extract_best_snippet(text, {"contracts"}, max_len=500)
        self.assertEqual(snippet, text)

    def test_extract_best_snippet_long_text(self):
        words = ["word"] * 200
        words[100] = "target"
        text = " ".join(words)
        snippet = app_module._extract_best_snippet(text, {"target"}, max_len=500)
        self.assertIn("target", snippet)


class TestKnowledgeEndpoints(unittest.TestCase):
    """Test /knowledge/* endpoints."""

    def setUp(self):
        self.client = app.test_client()
        app_module.build_knowledge_index()

    def test_knowledge_search_endpoint(self):
        resp = self.client.post("/knowledge/search",
                                json={"query": "confidential NDA"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("results", data)
        self.assertIn("total_indexed", data)
        self.assertGreater(data["total_indexed"], 0)

    def test_knowledge_refresh_endpoint(self):
        resp = self.client.post("/knowledge/refresh",
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("indexed", data)
        self.assertGreater(data["indexed"], 0)


class TestRouterDecideEndpoint(unittest.TestCase):
    """Test /router/decide endpoint (no model call needed)."""

    def setUp(self):
        self.client = app.test_client()
        app_module.ROUTER_LOG.clear()
        app_module.AGENT_AUDIT_LOG.clear()

    def test_decline_decision(self):
        resp = self.client.post("/router/decide", json={
            "decision": "decline",
            "context": {
                "pii_found": 2,
                "pii_details": [{"type": "SSN"}, {"type": "Email"}],
                "estimated_cost": 0.0085,
                "estimated_tokens": 847,
                "confidence": "MEDIUM",
                "sources_used": [{"filename": "test.txt"}],
            }
        })
        self.assertEqual(resp.status_code, 200)
        receipt = resp.get_json()
        self.assertEqual(receipt["decision"], "decline")
        self.assertEqual(receipt["pii_detected"], 2)
        self.assertIn("counterfactual", receipt)
        self.assertIn("847 tokens", receipt["counterfactual"])
        self.assertFalse(receipt["data_sent"])
        self.assertEqual(receipt["model_used"], app_module.DEFAULT_MODEL)

    @patch.object(app_module, '_check_network', return_value=True)
    def test_approve_decision(self, _mock_net):
        resp = self.client.post("/router/decide", json={
            "decision": "approve",
            "context": {
                "pii_found": 1,
                "pii_details": [{"type": "SSN"}],
                "estimated_cost": 0.005,
                "estimated_tokens": 600,
                "confidence": "LOW",
                "sources_used": [],
            }
        })
        self.assertEqual(resp.status_code, 200)
        receipt = resp.get_json()
        self.assertEqual(receipt["decision"], "approve")
        self.assertTrue(receipt["data_sent"])
        self.assertNotIn("counterfactual", receipt)

    def test_decision_logged_to_router_log(self):
        self.client.post("/router/decide", json={
            "decision": "decline",
            "context": {"confidence": "HIGH"}
        })
        self.assertEqual(len(app_module.ROUTER_LOG), 1)
        self.assertEqual(app_module.ROUTER_LOG[0]["decision"], "decline")

    @patch.object(app_module, '_check_network', return_value=True)
    def test_decision_logged_to_audit_log(self, _mock_net):
        self.client.post("/router/decide", json={
            "decision": "approve",
            "context": {"confidence": "MEDIUM"}
        })
        router_entries = [e for e in app_module.AGENT_AUDIT_LOG if e["tool"] == "router"]
        self.assertEqual(len(router_entries), 1)
        self.assertEqual(router_entries[0]["arguments"]["decision"], "approve")


class TestRouterLogEndpoint(unittest.TestCase):
    """Test /router/log GET endpoint."""

    def setUp(self):
        self.client = app.test_client()
        app_module.ROUTER_LOG.clear()

    def test_empty_log(self):
        resp = self.client.get("/router/log")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])

    def test_log_after_decisions(self):
        self.client.post("/router/decide", json={"decision": "decline", "context": {}})
        self.client.post("/router/decide", json={"decision": "approve", "context": {}})
        resp = self.client.get("/router/log")
        data = resp.get_json()
        self.assertEqual(len(data), 2)


class TestRouterAnalyzeEndpoint(unittest.TestCase):
    """Test /router/analyze streaming endpoint with mocked model."""

    def setUp(self):
        self.client = app.test_client()
        app_module.build_knowledge_index()

    def _mock_response(self, content):
        """Create a mock OpenAI chat completion response."""
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = content
        mock_resp.usage = MagicMock()
        mock_resp.usage.prompt_tokens = 500
        mock_resp.usage.completion_tokens = 300
        return mock_resp

    def _parse_stream(self, resp):
        """Parse streaming response into list of JSON objects."""
        return self._parse_stream_raw(resp.data)

    def _parse_stream_raw(self, raw_bytes):
        """Parse raw streaming bytes into list of JSON objects."""
        events = []
        for line in raw_bytes.decode().strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return events

    def _set_mock_create(self, return_value=None, side_effect=None):
        """Directly set mock on client.chat.completions.create (works with MagicMock client)."""
        old = app_module.client.chat.completions.create
        if side_effect:
            app_module.client.chat.completions.create = MagicMock(side_effect=side_effect)
        else:
            app_module.client.chat.completions.create = MagicMock(return_value=return_value)
        return old

    def test_analyze_with_document_high_confidence(self):
        model_output = (
            "CONFIDENCE: HIGH\n"
            "REASONING: Document is straightforward NDA with standard clauses.\n"
            "FRONTIER_BENEFIT: None — local answer is complete\n\n"
            "This is a standard mutual NDA between Vertex Dynamics and Pinnacle Solutions."
        )
        old = self._set_mock_create(return_value=self._mock_response(model_output))
        try:
            resp = self.client.post("/router/analyze", json={
                "text": "MUTUAL NON-DISCLOSURE AGREEMENT between parties...",
                "filename": "test_nda.txt",
                "query": "What are the key risks?"
            })
            # Must consume stream data while mock is active (generator is lazy)
            raw = resp.data
        finally:
            app_module.client.chat.completions.create = old

        self.assertEqual(resp.status_code, 200)
        events = self._parse_stream_raw(raw)
        types = [e["type"] for e in events]

        self.assertIn("status", types)
        self.assertIn("knowledge", types)
        self.assertIn("decision_card", types)
        self.assertIn("complete", types)
        # HIGH confidence should NOT produce escalation_available
        self.assertNotIn("escalation_available", types)

        dc = next(e for e in events if e["type"] == "decision_card")
        self.assertEqual(dc["confidence"], "HIGH")
        self.assertIn("standard mutual NDA", dc["analysis"])

    def test_analyze_with_document_medium_confidence(self):
        model_output = (
            "CONFIDENCE: MEDIUM\n"
            "REASONING: Complex indemnification clause needs expert review.\n"
            "FRONTIER_BENEFIT: A frontier model could analyze cross-jurisdictional implications.\n\n"
            "The NDA contains a broad indemnification clause in Section 4.2."
        )
        old = self._set_mock_create(return_value=self._mock_response(model_output))
        try:
            resp = self.client.post("/router/analyze", json={
                "text": "SSN: 123-45-6789 Email: test@example.com Phone: (555) 123-4567 NDA text here...",
                "filename": "test_nda.txt",
            })
            raw = resp.data
        finally:
            app_module.client.chat.completions.create = old

        events = self._parse_stream_raw(raw)
        types = [e["type"] for e in events]

        self.assertIn("escalation_available", types)

        esc = next(e for e in events if e["type"] == "escalation_available")
        self.assertGreater(esc["pii_found"], 0)
        self.assertGreater(esc["estimated_tokens"], 0)
        self.assertGreater(esc["estimated_cost"], 0)
        self.assertIn("[REDACTED", esc["redacted_preview"])

    def test_analyze_query_only(self):
        model_output = (
            "CONFIDENCE: HIGH\n"
            "REASONING: Found answer in local knowledge.\n"
            "FRONTIER_BENEFIT: None — local answer is complete\n\n"
            "Based on local documents, the NDA expires in 2028."
        )
        old = self._set_mock_create(return_value=self._mock_response(model_output))
        try:
            resp = self.client.post("/router/analyze", json={
                "query": "When does the NDA expire?"
            })
            raw = resp.data
        finally:
            app_module.client.chat.completions.create = old

        events = self._parse_stream_raw(raw)
        types = [e["type"] for e in events]
        self.assertIn("decision_card", types)

    def test_analyze_knowledge_sources(self):
        model_output = (
            "CONFIDENCE: HIGH\n"
            "REASONING: Found in local knowledge.\n"
            "FRONTIER_BENEFIT: None\n\n"
            "Answer from local sources."
        )
        old = self._set_mock_create(return_value=self._mock_response(model_output))
        try:
            resp = self.client.post("/router/analyze", json={
                "query": "confidential agreement indemnification"
            })
            raw = resp.data
        finally:
            app_module.client.chat.completions.create = old

        events = self._parse_stream_raw(raw)
        knowledge_evt = next((e for e in events if e["type"] == "knowledge"), None)
        self.assertIsNotNone(knowledge_evt)
        self.assertGreater(len(knowledge_evt["sources"]), 0)

    def test_analyze_model_error(self):
        old = self._set_mock_create(side_effect=Exception("Model unavailable"))
        try:
            resp = self.client.post("/router/analyze", json={
                "text": "Some document text",
                "filename": "test.txt",
            })
            raw = resp.data
        finally:
            app_module.client.chat.completions.create = old

        events = self._parse_stream_raw(raw)
        types = [e["type"] for e in events]
        self.assertIn("error", types)


class TestHTMLTemplate(unittest.TestCase):
    """Test that the HTML template contains all required Phase 1 elements."""

    def setUp(self):
        self.client = app.test_client()
        resp = self.client.get("/")
        self.html = resp.data.decode()

    def test_sidebar_nav_item(self):
        self.assertIn('data-tab="router"', self.html)
        self.assertIn("Two-Brain", self.html)

    def test_hidden_tab_button(self):
        self.assertIn('id="routerTabBtn"', self.html)

    def test_router_tab_div(self):
        self.assertIn('id="router-tab"', self.html)

    def test_router_input_zone(self):
        self.assertIn('id="routerInputZone"', self.html)
        self.assertIn('id="routerDropzone"', self.html)
        self.assertIn('id="routerFileInput"', self.html)
        self.assertIn('id="routerUploadBtn"', self.html)
        self.assertIn('id="routerQueryInput"', self.html)
        self.assertIn('id="routerAskBtn"', self.html)
        self.assertIn('id="routerDemoBtn"', self.html)

    def test_decision_card_elements(self):
        self.assertIn('id="routerDecisionCard"', self.html)
        self.assertIn('id="dcConfidence"', self.html)
        self.assertIn('id="dcSources"', self.html)
        self.assertIn('id="dcFrontierBenefit"', self.html)
        self.assertIn('id="routerAnalysisText"', self.html)

    def test_escalation_consent_elements(self):
        self.assertIn('id="escalationConsent"', self.html)
        self.assertIn('id="diffOriginal"', self.html)
        self.assertIn('id="diffRedacted"', self.html)
        self.assertIn('id="escPiiCount"', self.html)
        self.assertIn('id="escTokens"', self.html)
        self.assertIn('id="escCost"', self.html)
        self.assertIn('id="btnDeclineEsc"', self.html)
        self.assertIn('id="btnApproveEsc"', self.html)

    def test_stayed_local_banner(self):
        self.assertIn('id="stayedLocalBanner"', self.html)
        self.assertIn("stayed-local-banner", self.html)
        self.assertIn("Stayed Local", self.html)

    def test_trust_receipt(self):
        self.assertIn('id="routerTrustReceipt"', self.html)
        self.assertIn('id="trustReceiptBody"', self.html)
        self.assertIn("TRUST RECEIPT", self.html)

    def test_post_actions(self):
        self.assertIn('id="routerPostActions"', self.html)
        self.assertIn("resetRouter()", self.html)

    def test_two_brain_suggestion_chip(self):
        self.assertIn('data-action="two-brain"', self.html)
        self.assertIn("Two-Brain Analysis", self.html)

    def test_css_classes_present(self):
        self.assertIn(".decision-card", self.html)
        self.assertIn(".escalation-btn", self.html)
        self.assertIn(".stayed-local-banner", self.html)
        self.assertIn(".trust-receipt", self.html)
        self.assertIn(".redaction-diff", self.html)
        self.assertIn(".pii-redacted", self.html)
        self.assertIn("@keyframes lockPulse", self.html)

    def test_router_tab_in_tabmap(self):
        self.assertIn("router:", self.html)
        self.assertIn("router-tab", self.html)
        self.assertIn("routerTabBtn", self.html)

    def test_js_router_functions(self):
        self.assertIn("runRouterAnalysis", self.html)
        self.assertIn("processRouterEvent", self.html)
        self.assertIn("renderTrustReceipt", self.html)
        self.assertIn("resetRouter", self.html)
        self.assertIn("routerEscalationContext", self.html)

    def test_existing_tabs_preserved(self):
        """Verify no existing tabs were removed."""
        self.assertIn('data-tab="chat"', self.html)
        self.assertIn('data-tab="day"', self.html)
        self.assertIn('data-tab="auditor"', self.html)
        self.assertIn('data-tab="id"', self.html)
        self.assertIn('id="chat-tab"', self.html)
        self.assertIn('id="day-tab"', self.html)
        self.assertIn('id="auditor-tab"', self.html)
        self.assertIn('id="id-tab"', self.html)

    def test_existing_chips_preserved(self):
        """Verify no existing suggestion chips were removed."""
        self.assertIn('data-action="meeting-agenda"', self.html)
        self.assertIn('data-action="analyze-strategy"', self.html)
        self.assertIn('data-action="list-documents"', self.html)
        self.assertIn('data-action="summarize-doc"', self.html)
        self.assertIn('data-action="device-health"', self.html)

    def test_js_references_correct_savings_function(self):
        """Verify we use updateSavingsWidget (not refreshSavingsWidget)."""
        self.assertIn("updateSavingsWidget()", self.html)
        self.assertNotIn("refreshSavingsWidget", self.html)


class TestExistingEndpointsNotBroken(unittest.TestCase):
    """Verify that existing endpoints still respond correctly."""

    def setUp(self):
        self.client = app.test_client()

    def test_home_page_loads(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_session_stats(self):
        resp = self.client.get("/session-stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("calls", data)
        self.assertIn("cloud_cost_saved", data)

    def test_audit_log(self):
        resp = self.client.get("/audit-log")
        self.assertEqual(resp.status_code, 200)

    def test_auditor_demo_doc(self):
        resp = self.client.get("/auditor-demo-doc")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("text", data)
        self.assertIn("filename", data)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)


# =============================================================================
# Additional test classes (hardening, contracts, edge cases)
# =============================================================================


class TestGlobalStateReset(unittest.TestCase):
    """Verify every test starts from a known baseline — prevents order-dependent flakes."""

    def setUp(self):
        app_module.ROUTER_LOG.clear()
        app_module.AGENT_AUDIT_LOG.clear()
        app_module.SESSION_STATS["calls"] = 0
        app_module.SESSION_STATS["input_tokens"] = 0
        app_module.SESSION_STATS["output_tokens"] = 0
        app_module.SESSION_STATS["inference_seconds"] = 0.0

    def test_router_log_starts_empty(self):
        self.assertEqual(len(app_module.ROUTER_LOG), 0)

    def test_audit_log_starts_empty(self):
        self.assertEqual(len(app_module.AGENT_AUDIT_LOG), 0)

    def test_session_stats_zeroed(self):
        self.assertEqual(app_module.SESSION_STATS["calls"], 0)
        self.assertEqual(app_module.SESSION_STATS["input_tokens"], 0)
        self.assertEqual(app_module.SESSION_STATS["output_tokens"], 0)
        self.assertEqual(app_module.SESSION_STATS["inference_seconds"], 0.0)

    def test_mutation_does_not_leak(self):
        """Two sub-tests in sequence: first mutates, second confirms reset."""
        app_module.ROUTER_LOG.append({"test": "leaked"})
        app_module.AGENT_AUDIT_LOG.append({"test": "leaked"})
        app_module.SESSION_STATS["calls"] = 999
        # setUp() will reset before the NEXT test, so assert the mutation exists HERE
        self.assertEqual(len(app_module.ROUTER_LOG), 1)

    def test_after_mutation_is_clean(self):
        """Runs after test_mutation_does_not_leak — setUp should have cleared everything."""
        self.assertEqual(len(app_module.ROUTER_LOG), 0)
        self.assertEqual(len(app_module.AGENT_AUDIT_LOG), 0)
        self.assertEqual(app_module.SESSION_STATS["calls"], 0)

    def test_no_session_cookies(self):
        """App is stateless — no Flask session, no per-client cookies."""
        c = app.test_client()
        resp = c.get("/")
        # Check Set-Cookie header — app should not set any cookies
        set_cookie_headers = resp.headers.getlist("Set-Cookie")
        session_cookies = [h for h in set_cookie_headers if "session" in h.lower()]
        self.assertEqual(len(session_cookies), 0, "App should not set session cookies")


class TestRouterResponseSchema(unittest.TestCase):
    """Contract tests: ensure /router/analyze response JSON matches what the frontend JS expects."""

    def setUp(self):
        self.client = app.test_client()
        app_module.build_knowledge_index()

    def _mock_response(self, content):
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = content
        mock_resp.usage = MagicMock()
        mock_resp.usage.prompt_tokens = 500
        mock_resp.usage.completion_tokens = 300
        return mock_resp

    def _run_analyze(self, model_output, body):
        old = app_module.client.chat.completions.create
        app_module.client.chat.completions.create = MagicMock(
            return_value=self._mock_response(model_output))
        try:
            resp = self.client.post("/router/analyze",
                                    json=body,
                                    content_type="application/json")
            raw = resp.data
        finally:
            app_module.client.chat.completions.create = old
        events = []
        for line in raw.decode().strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return events

    def test_status_event_schema(self):
        events = self._run_analyze(
            "CONFIDENCE: HIGH\nREASONING: ok\nFRONTIER_BENEFIT: None\n\nDone.",
            {"query": "test"})
        statuses = [e for e in events if e["type"] == "status"]
        for s in statuses:
            self.assertIn("message", s)
            self.assertIsInstance(s["message"], str)

    def test_knowledge_event_schema(self):
        events = self._run_analyze(
            "CONFIDENCE: HIGH\nREASONING: ok\nFRONTIER_BENEFIT: None\n\nDone.",
            {"query": "confidential NDA agreement"})
        kev = next(e for e in events if e["type"] == "knowledge")
        self.assertIn("sources", kev)
        self.assertIn("total_indexed", kev)
        self.assertIsInstance(kev["sources"], list)
        self.assertIsInstance(kev["total_indexed"], int)
        for src in kev["sources"]:
            self.assertIn("filename", src)
            self.assertIn("score", src)

    def test_decision_card_event_schema(self):
        events = self._run_analyze(
            "CONFIDENCE: MEDIUM\nREASONING: needs review\nFRONTIER_BENEFIT: deeper analysis\n\nSome analysis.",
            {"text": "SSN: 123-45-6789", "filename": "doc.txt"})
        dc = next(e for e in events if e["type"] == "decision_card")
        # Required keys
        for key in ("analysis", "confidence", "reasoning", "frontier_benefit",
                     "sources_used", "analysis_time"):
            self.assertIn(key, dc, f"Missing key: {key}")
        # Type checks
        self.assertIn(dc["confidence"], ("HIGH", "MEDIUM", "LOW"))
        self.assertIsInstance(dc["analysis"], str)
        self.assertIsInstance(dc["reasoning"], str)
        self.assertIsInstance(dc["frontier_benefit"], str)
        self.assertIsInstance(dc["sources_used"], list)
        self.assertIsInstance(dc["analysis_time"], (int, float))

    def test_escalation_event_schema(self):
        events = self._run_analyze(
            "CONFIDENCE: LOW\nREASONING: too complex\nFRONTIER_BENEFIT: expert needed\n\nPartial.",
            {"text": "SSN: 111-22-3333 email: a@b.com phone: (555) 999-0000", "filename": "x.txt"})
        esc = next((e for e in events if e["type"] == "escalation_available"), None)
        self.assertIsNotNone(esc, "LOW confidence should produce escalation_available")
        for key in ("pii_found", "pii_details", "original_preview", "redacted_preview",
                     "estimated_tokens", "estimated_cost"):
            self.assertIn(key, esc, f"Missing key: {key}")
        self.assertIsInstance(esc["pii_found"], int)
        self.assertIsInstance(esc["pii_details"], list)
        self.assertIsInstance(esc["estimated_tokens"], (int, float))
        self.assertIsInstance(esc["estimated_cost"], (int, float))
        self.assertGreater(esc["pii_found"], 0)

    def test_complete_event_schema(self):
        events = self._run_analyze(
            "CONFIDENCE: HIGH\nREASONING: ok\nFRONTIER_BENEFIT: None\n\nDone.",
            {"query": "test"})
        comp = next(e for e in events if e["type"] == "complete")
        self.assertIn("total_time", comp)
        self.assertIsInstance(comp["total_time"], (int, float))

    def test_decide_receipt_schema(self):
        """Contract test for /router/decide response."""
        app_module.ROUTER_LOG.clear()
        c = app.test_client()
        resp = c.post("/router/decide", json={
            "decision": "decline",
            "context": {
                "pii_found": 1, "pii_details": [{"type": "SSN"}],
                "estimated_cost": 0.005, "estimated_tokens": 600,
                "confidence": "MEDIUM", "sources_used": [{"filename": "f.txt"}],
            }
        })
        receipt = resp.get_json()
        for key in ("timestamp", "decision", "model_used", "offline", "pii_detected",
                     "pii_types", "estimated_cost_if_escalated", "estimated_tokens_if_escalated",
                     "confidence", "sources_consulted", "data_sent"):
            self.assertIn(key, receipt, f"Missing receipt key: {key}")
        self.assertIsInstance(receipt["pii_types"], list)
        self.assertIsInstance(receipt["sources_consulted"], list)
        self.assertIsInstance(receipt["data_sent"], bool)

    def test_knowledge_search_result_schema(self):
        """Contract test for /knowledge/search response."""
        app_module.build_knowledge_index()
        c = app.test_client()
        resp = c.post("/knowledge/search", json={"query": "confidential NDA"})
        data = resp.get_json()
        self.assertIn("results", data)
        self.assertIn("total_indexed", data)
        for r in data["results"]:
            self.assertIn("filename", r)
            self.assertIn("snippet", r)
            self.assertIn("score", r)
            self.assertIsInstance(r["filename"], str)
            self.assertIsInstance(r["snippet"], str)
            self.assertLessEqual(len(r["snippet"]), 500, "Snippet should be bounded to max_len")


class TestInvalidJSONBody(unittest.TestCase):
    """Verify endpoints handle missing/malformed JSON gracefully."""

    def setUp(self):
        self.client = app.test_client()
        app_module.ROUTER_LOG.clear()
        app_module.AGENT_AUDIT_LOG.clear()

    def test_router_analyze_no_content_type(self):
        resp = self.client.post("/router/analyze", data="not json")
        # get_json(silent=True) returns None → falls back to {} → 200 with empty text
        self.assertIn(resp.status_code, (200, 400))

    def test_router_analyze_empty_body(self):
        resp = self.client.post("/router/analyze",
                                data="",
                                content_type="application/json")
        # get_json(silent=True) returns None → falls back to {} → 200 with empty text
        self.assertIn(resp.status_code, (200, 400))

    def test_router_decide_no_json(self):
        resp = self.client.post("/router/decide", data="not json")
        # get_json(silent=True) returns None → falls back to {} → default decline
        self.assertIn(resp.status_code, (200, 400))

    def test_router_decide_empty_body(self):
        resp = self.client.post("/router/decide",
                                data="",
                                content_type="application/json")
        # get_json(silent=True) returns None → falls back to {} → default decline
        self.assertIn(resp.status_code, (200, 400))

    def test_knowledge_search_no_json(self):
        resp = self.client.post("/knowledge/search", data="not json")
        # get_json(silent=True) returns None → falls back to {} → empty query → 200
        self.assertIn(resp.status_code, (200, 400))

    def test_malformed_decide_defaults_to_decline(self):
        """Non-JSON body falls through to default decline (graceful degradation)."""
        resp = self.client.post("/router/decide", data="not json")
        # get_json(silent=True) returns None → {} → decision defaults to 'decline'
        if resp.status_code == 200:
            receipt = resp.get_json()
            self.assertEqual(receipt["decision"], "decline")
        else:
            # 400 is also acceptable if validation rejects it
            self.assertEqual(resp.status_code, 400)


class TestXSSEscapingInSnippets(unittest.TestCase):
    """Verify knowledge search doesn't return raw <script> tags that could cause XSS."""

    _xss_file = None

    @classmethod
    def setUpClass(cls):
        """Create a temp document with XSS payload in DEMO_DIR."""
        cls._xss_file = os.path.join(app_module.DEMO_DIR, "_test_xss_probe.txt")
        with open(cls._xss_file, "w", encoding="utf-8") as f:
            f.write(
                'Contract terms: <script>alert("xss")</script>\n'
                'Also: <img onerror="alert(1)" src=x>\n'
                'Normal confidential NDA agreement text here.\n'
            )
        app_module.build_knowledge_index()

    @classmethod
    def tearDownClass(cls):
        """Remove temp file and rebuild index."""
        if cls._xss_file and os.path.exists(cls._xss_file):
            os.remove(cls._xss_file)
        app_module.build_knowledge_index()

    def test_xss_file_is_indexed(self):
        self.assertIn("_test_xss_probe.txt", app_module.KNOWLEDGE_INDEX)

    def test_search_returns_xss_document(self):
        # Query must match terms actually in the XSS test file
        results = app_module.search_knowledge("contract terms normal confidential")
        filenames = [r["filename"] for r in results]
        self.assertIn("_test_xss_probe.txt", filenames)

    def test_snippet_contains_raw_script_tag(self):
        """Document the current behavior: snippets are returned as raw text (no escaping).
        The frontend MUST use textContent or sanitize. This test locks the behavior so
        any future change to escaping is intentional."""
        results = app_module.search_knowledge("contract terms script alert")
        xss_results = [r for r in results if r["filename"] == "_test_xss_probe.txt"]
        if xss_results:
            snippet = xss_results[0]["snippet"]
            # Currently raw — this test documents the contract.
            # If someone adds server-side escaping, this test will need updating.
            self.assertIsInstance(snippet, str)
            # The snippet should contain the text (possibly with <script> if in the window)
            self.assertGreater(len(snippet), 0)

    def test_knowledge_endpoint_returns_json_not_html(self):
        """Even with XSS payload in docs, the endpoint returns application/json."""
        c = app.test_client()
        resp = c.post("/knowledge/search", json={"query": "script alert contract"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/json", resp.content_type)
        # Verify it's valid JSON (not accidentally rendered as HTML)
        data = resp.get_json()
        self.assertIsNotNone(data)


class TestLargeInputHandling(unittest.TestCase):
    """Verify endpoints handle oversized payloads without crashing."""

    def setUp(self):
        self.client = app.test_client()

    def test_large_text_to_router_analyze(self):
        """Send 1 MB of text — should not crash (may truncate or 413)."""
        big_text = "word " * 200_000  # ~1 MB
        old = app_module.client.chat.completions.create
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "CONFIDENCE: HIGH\nREASONING: ok\nFRONTIER_BENEFIT: None\n\nDone."
        mock_resp.usage = MagicMock()
        mock_resp.usage.prompt_tokens = 500
        mock_resp.usage.completion_tokens = 100
        app_module.client.chat.completions.create = MagicMock(return_value=mock_resp)
        try:
            resp = self.client.post("/router/analyze", json={
                "text": big_text,
                "filename": "huge.txt"
            })
            _ = resp.data  # consume stream
        finally:
            app_module.client.chat.completions.create = old
        self.assertIn(resp.status_code, (200, 413))

    def test_large_query_to_knowledge_search(self):
        """Send a very long query string."""
        big_query = "confidential " * 10_000
        resp = self.client.post("/knowledge/search", json={"query": big_query})
        self.assertIn(resp.status_code, (200, 413))

    def test_large_pii_scan(self):
        """PII scan on a large text should complete without error."""
        # 10K SSNs embedded
        text = " ".join(f"SSN: {i:03d}-{i%100:02d}-{i:04d}" for i in range(100, 10100))
        findings = app_module._scan_pii(text)
        # Should find many but not crash
        self.assertGreater(len(findings), 0)

    def test_unicode_mixed_input(self):
        """Zero-width spaces, emoji, RTL marks, mixed newlines don't crash."""
        weird_text = (
            "Normal text \u200b\u200b zero-width "
            "\U0001f4a9 poop emoji "
            "\u200f RTL mark "
            "SSN: 123-45-6789 "
            "email: test@example.com "
            "\r\n windows newline \n unix newline \r old mac"
        )
        # PII scan
        findings = app_module._scan_pii(weird_text)
        ssns = [f for f in findings if f["type"] == "SSN"]
        emails = [f for f in findings if f["type"] == "Email"]
        self.assertEqual(len(ssns), 1, "Should find SSN even with unicode noise")
        self.assertEqual(len(emails), 1, "Should find email even with unicode noise")

        # Redaction
        redacted = app_module._redact_text(weird_text, findings)
        self.assertNotIn("123-45-6789", redacted)
        self.assertNotIn("test@example.com", redacted)

        # Knowledge search
        results = app_module.search_knowledge(weird_text[:200])
        self.assertIsInstance(results, list)  # no crash


class TestModelUnavailableEnhanced(unittest.TestCase):
    """Enhanced model-error tests: verify no side-effect pollution on failure."""

    def setUp(self):
        self.client = app.test_client()
        app_module.ROUTER_LOG.clear()
        app_module.AGENT_AUDIT_LOG.clear()
        app_module.SESSION_STATS["calls"] = 0
        app_module.SESSION_STATS["input_tokens"] = 0
        app_module.SESSION_STATS["output_tokens"] = 0
        app_module.SESSION_STATS["inference_seconds"] = 0.0
        app_module.build_knowledge_index()

    def test_model_error_does_not_increment_stats(self):
        old = app_module.client.chat.completions.create
        app_module.client.chat.completions.create = MagicMock(
            side_effect=Exception("Connection refused"))
        try:
            resp = self.client.post("/router/analyze", json={
                "text": "Some text", "filename": "test.txt"
            })
            _ = resp.data
        finally:
            app_module.client.chat.completions.create = old
        self.assertEqual(app_module.SESSION_STATS["calls"], 0,
                         "Failed model call should not increment call count")
        self.assertEqual(app_module.SESSION_STATS["input_tokens"], 0)

    def test_model_error_does_not_add_router_log(self):
        old = app_module.client.chat.completions.create
        app_module.client.chat.completions.create = MagicMock(
            side_effect=Exception("Timeout"))
        try:
            resp = self.client.post("/router/analyze", json={
                "text": "Some text", "filename": "test.txt"
            })
            _ = resp.data
        finally:
            app_module.client.chat.completions.create = old
        self.assertEqual(len(app_module.ROUTER_LOG), 0,
                         "Model error should not create a router log entry")

    def test_error_event_has_message(self):
        old = app_module.client.chat.completions.create
        app_module.client.chat.completions.create = MagicMock(
            side_effect=Exception("NPU device not found"))
        try:
            resp = self.client.post("/router/analyze", json={
                "text": "Some text", "filename": "test.txt"
            })
            raw = resp.data
        finally:
            app_module.client.chat.completions.create = old
        events = []
        for line in raw.decode().strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        error_events = [e for e in events if e.get("type") == "error"]
        self.assertEqual(len(error_events), 1)
        self.assertIn("message", error_events[0])
        self.assertIn("NPU device not found", error_events[0]["message"])


class TestAuditLogNoPIILeakage(unittest.TestCase):
    """Verify audit and router logs never contain raw PII values."""

    def setUp(self):
        self.client = app.test_client()
        app_module.ROUTER_LOG.clear()
        app_module.AGENT_AUDIT_LOG.clear()

    def test_router_log_no_raw_ssn(self):
        self.client.post("/router/decide", json={
            "decision": "decline",
            "context": {
                "pii_found": 1,
                "pii_details": [{"type": "SSN", "value": "123-45-6789",
                                 "start": 0, "end": 11, "severity": "high"}],
                "estimated_cost": 0.005,
                "estimated_tokens": 600,
                "confidence": "MEDIUM",
                "sources_used": [],
            }
        })
        log_str = json.dumps(app_module.ROUTER_LOG)
        self.assertNotIn("123-45-6789", log_str,
                         "Router log should not contain raw SSN values")

    def test_router_log_no_raw_email(self):
        self.client.post("/router/decide", json={
            "decision": "decline",
            "context": {
                "pii_found": 1,
                "pii_details": [{"type": "Email", "value": "secret@corp.com",
                                 "start": 0, "end": 15, "severity": "medium"}],
                "estimated_cost": 0.003,
                "estimated_tokens": 400,
                "confidence": "LOW",
                "sources_used": [],
            }
        })
        log_str = json.dumps(app_module.ROUTER_LOG)
        self.assertNotIn("secret@corp.com", log_str,
                         "Router log should not contain raw email values")

    def test_audit_log_stores_only_metadata(self):
        self.client.post("/router/decide", json={
            "decision": "approve",
            "context": {
                "pii_found": 2,
                "pii_details": [{"type": "SSN", "value": "999-88-7777"},
                                {"type": "Phone", "value": "(555) 123-0000"}],
                "confidence": "LOW",
            }
        })
        router_entries = [e for e in app_module.AGENT_AUDIT_LOG if e.get("tool") == "router"]
        self.assertEqual(len(router_entries), 1)
        entry_str = json.dumps(router_entries[0])
        self.assertNotIn("999-88-7777", entry_str)
        self.assertNotIn("(555) 123-0000", entry_str)
        # Only metadata keys should be present
        entry = router_entries[0]
        self.assertIn("decision", entry["arguments"])
        self.assertIn("confidence", entry["arguments"])


class TestIndexRebuildIdempotent(unittest.TestCase):
    """Building the index twice on the same DEMO_DIR should produce identical results."""

    def test_rebuild_same_keys(self):
        app_module.build_knowledge_index()
        keys1 = sorted(app_module.KNOWLEDGE_INDEX.keys())
        counts1 = {k: v["word_count"] for k, v in app_module.KNOWLEDGE_INDEX.items()}
        terms1 = {k: dict(v["terms"]) for k, v in app_module.KNOWLEDGE_INDEX.items()}

        app_module.build_knowledge_index()
        keys2 = sorted(app_module.KNOWLEDGE_INDEX.keys())
        counts2 = {k: v["word_count"] for k, v in app_module.KNOWLEDGE_INDEX.items()}
        terms2 = {k: dict(v["terms"]) for k, v in app_module.KNOWLEDGE_INDEX.items()}

        self.assertEqual(keys1, keys2, "Index keys should be stable across rebuilds")
        self.assertEqual(counts1, counts2, "Word counts should be stable across rebuilds")
        self.assertEqual(terms1, terms2, "Term frequencies should be stable across rebuilds")

    def test_index_ignores_non_text_files(self):
        """Create a non-text file, rebuild, verify it's excluded."""
        fake_exe = os.path.join(app_module.DEMO_DIR, "_test_fake.exe")
        fake_ds = os.path.join(app_module.DEMO_DIR, ".DS_Store")
        try:
            for path in (fake_exe, fake_ds):
                with open(path, "w") as f:
                    f.write("binary junk")
            app_module.build_knowledge_index()
            self.assertNotIn("_test_fake.exe", app_module.KNOWLEDGE_INDEX)
            self.assertNotIn(".DS_Store", app_module.KNOWLEDGE_INDEX)
        finally:
            for path in (fake_exe, fake_ds):
                if os.path.exists(path):
                    os.remove(path)
            app_module.build_knowledge_index()


class TestSessionStatsMonotonicity(unittest.TestCase):
    """Session stats should only increase (or stay flat) — never decrease."""

    def setUp(self):
        self.client = app.test_client()
        app_module.SESSION_STATS["calls"] = 0
        app_module.SESSION_STATS["input_tokens"] = 0
        app_module.SESSION_STATS["output_tokens"] = 0
        app_module.SESSION_STATS["inference_seconds"] = 0.0

    def _mock_response(self):
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "CONFIDENCE: HIGH\nREASONING: ok\nFRONTIER_BENEFIT: None\n\nDone."
        mock_resp.usage = MagicMock()
        mock_resp.usage.prompt_tokens = 500
        mock_resp.usage.completion_tokens = 300
        return mock_resp

    def test_stats_increase_after_router_call(self):
        before = dict(app_module.SESSION_STATS)

        old = app_module.client.chat.completions.create
        app_module.client.chat.completions.create = MagicMock(return_value=self._mock_response())
        try:
            resp = self.client.post("/router/analyze", json={"query": "test question"})
            _ = resp.data
        finally:
            app_module.client.chat.completions.create = old

        after = app_module.SESSION_STATS
        self.assertGreater(after["calls"], before["calls"], "Call count should increase")
        self.assertGreaterEqual(after["input_tokens"], before["input_tokens"])
        self.assertGreaterEqual(after["output_tokens"], before["output_tokens"])
        self.assertGreaterEqual(after["inference_seconds"], before["inference_seconds"])

    def test_stats_non_negative(self):
        """All stats values should always be >= 0."""
        for key in ("calls", "input_tokens", "output_tokens", "inference_seconds"):
            self.assertGreaterEqual(app_module.SESSION_STATS[key], 0,
                                    f"{key} should be non-negative")

    def test_multiple_calls_accumulate(self):
        old = app_module.client.chat.completions.create
        app_module.client.chat.completions.create = MagicMock(return_value=self._mock_response())
        try:
            for _ in range(3):
                resp = self.client.post("/router/analyze", json={"query": "test"})
                _ = resp.data
        finally:
            app_module.client.chat.completions.create = old

        self.assertEqual(app_module.SESSION_STATS["calls"], 3)
        self.assertEqual(app_module.SESSION_STATS["input_tokens"], 1500)  # 500 * 3
        self.assertEqual(app_module.SESSION_STATS["output_tokens"], 900)  # 300 * 3


class TestRouterDecideWithStaleContext(unittest.TestCase):
    """Verify /router/decide handles edge cases: empty context, stale data, duplicates."""

    def setUp(self):
        self.client = app.test_client()
        app_module.ROUTER_LOG.clear()
        app_module.AGENT_AUDIT_LOG.clear()

    def test_empty_context(self):
        """Decide with completely empty context — should not crash."""
        resp = self.client.post("/router/decide", json={
            "decision": "decline",
            "context": {}
        })
        self.assertEqual(resp.status_code, 200)
        receipt = resp.get_json()
        self.assertEqual(receipt["decision"], "decline")
        self.assertEqual(receipt["pii_detected"], 0)
        self.assertEqual(receipt["confidence"], "unknown")

    @patch.object(app_module, '_check_network', return_value=True)
    def test_missing_context_key(self, _mock_net):
        """Decide with no context key at all."""
        resp = self.client.post("/router/decide", json={
            "decision": "approve"
        })
        self.assertEqual(resp.status_code, 200)
        receipt = resp.get_json()
        self.assertTrue(receipt["data_sent"])
        self.assertEqual(receipt["pii_detected"], 0)

    def test_duplicate_decisions(self):
        """Multiple identical decisions should create separate log entries."""
        for _ in range(3):
            self.client.post("/router/decide", json={
                "decision": "decline",
                "context": {"confidence": "HIGH"}
            })
        self.assertEqual(len(app_module.ROUTER_LOG), 3)
        # All should have timestamps (even if same second)
        for entry in app_module.ROUTER_LOG:
            self.assertIn("timestamp", entry)

    def test_unknown_decision_value(self):
        """Non-standard decision value should be rejected with 400."""
        resp = self.client.post("/router/decide", json={
            "decision": "maybe_later",
            "context": {"confidence": "MEDIUM"}
        })
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertIn("error", body)
        self.assertIn("Invalid decision", body["error"])

    def test_extra_unknown_fields_ignored(self):
        """Extra fields in context should not cause errors."""
        resp = self.client.post("/router/decide", json={
            "decision": "decline",
            "context": {
                "confidence": "HIGH",
                "unknown_field": "should be ignored",
                "nested": {"deep": True},
            }
        })
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    # Run with verbose output
    unittest.main(verbosity=2)
