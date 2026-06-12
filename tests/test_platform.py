"""Platform-layer tests: rate-limit identity and bounds, the request-body cap,
auth comparison, request-id hygiene, and the Gemini retry budget contract."""

import importlib
import json
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.security as security
from app.main import app


class GeminiResponse:
    def __init__(self, text):
        self.text = text


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"

VERIFY_REVIEWED_BODY = {
    "product_category": "wine",
    "origin_type": "domestic",
    "expected": {},
    "reviewed": {},
}


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        security._request_log.clear()  # don't let rate-limit state bleed across tests

    # --- client identity: X-Forwarded-For parsing -------------------------------

    def test_client_ip_uses_rightmost_valid_forwarded_ip(self):
        # The right-most entry is the one the nearest proxy appended; everything
        # left of it is client-supplied and must not mint a fresh bucket.
        response = self.client.post(
            "/verify-reviewed",
            json=VERIFY_REVIEWED_BODY,
            headers={"X-Forwarded-For": "203.0.113.7, 198.51.100.9"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("198.51.100.9", security._request_log)
        self.assertNotIn("203.0.113.7", security._request_log)

    def test_client_ip_skips_invalid_rightmost_candidates(self):
        response = self.client.post(
            "/verify-reviewed",
            json=VERIFY_REVIEWED_BODY,
            headers={"X-Forwarded-For": "198.51.100.9, garbage, "},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("198.51.100.9", security._request_log)

    def test_client_ip_falls_back_when_forwarded_header_invalid(self):
        # No syntactically valid IP anywhere in the header -> the socket peer
        # ("testclient" under TestClient) is used instead of a spoofable string.
        response = self.client.post(
            "/verify-reviewed",
            json=VERIFY_REVIEWED_BODY,
            headers={"X-Forwarded-For": "spoofed-identity, not-an-ip"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(security._request_log), ["testclient"])

    # --- rate-limit log bounds ---------------------------------------------------

    def test_request_log_capped_with_stalest_identifiers_evicted(self):
        with patch.object(security, "_MAX_TRACKED_IDENTIFIERS", 2):
            for ip in ("198.51.100.1", "198.51.100.2", "198.51.100.3"):
                response = self.client.post(
                    "/verify-reviewed", json=VERIFY_REVIEWED_BODY, headers={"X-Forwarded-For": ip}
                )
                self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(security._request_log), 2)
        self.assertIn("198.51.100.3", security._request_log)
        self.assertNotIn("198.51.100.1", security._request_log)  # stalest evicted first

    def test_request_log_drops_fully_aged_out_identifiers(self):
        # An identifier whose every entry has left the window is dead weight; the
        # overflow sweep must reclaim it before evicting anything live.
        security._request_log["198.51.100.250"].append(time.monotonic() - 2 * security.RATE_LIMIT_WINDOW_SECONDS)
        with patch.object(security, "_MAX_TRACKED_IDENTIFIERS", 1):
            response = self.client.post(
                "/verify-reviewed", json=VERIFY_REVIEWED_BODY, headers={"X-Forwarded-For": "198.51.100.9"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("198.51.100.250", security._request_log)
        self.assertIn("198.51.100.9", security._request_log)

    # --- 429 contract -------------------------------------------------------------

    def test_rate_limited_response_carries_retry_after(self):
        with patch.object(security, "RATE_LIMIT_REQUESTS", 1):
            first = self.client.post("/verify-reviewed", json=VERIFY_REVIEWED_BODY)
            second = self.client.post("/verify-reviewed", json=VERIFY_REVIEWED_BODY)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        # Retry-After is the batch-pacing contract: seconds until the oldest
        # logged request leaves the window, never less than 1.
        retry_after = int(second.headers["retry-after"])
        self.assertGreaterEqual(retry_after, 1)
        self.assertLessEqual(retry_after, security.RATE_LIMIT_WINDOW_SECONDS)
        self.assertEqual(second.json()["error"]["details"]["retry_after_seconds"], retry_after)

    # --- request-body cap ----------------------------------------------------------

    def test_declared_content_length_over_cap_rejected_with_request_id(self):
        with patch.object(security, "MAX_REQUEST_BYTES", 10):
            response = self.client.post("/verify-reviewed", json=VERIFY_REVIEWED_BODY)
        self.assertEqual(response.status_code, 413)
        error = response.json()["error"]
        self.assertEqual(error["code"], "REQUEST_TOO_LARGE")
        self.assertIn("request_id", error)  # same envelope contract as every other error
        self.assertTrue(response.headers.get("x-request-id"))

    def test_chunked_body_over_cap_rejected_mid_stream(self):
        # A generator body is sent chunked with no Content-Length, so only the
        # counted enforcement path can stop it.
        def chunks():
            for _ in range(4):
                yield b"x" * 8

        with patch.object(security, "MAX_REQUEST_BYTES", 10):
            response = self.client.post(
                "/verify-reviewed", content=chunks(), headers={"Content-Type": "application/json"}
            )
        self.assertEqual(response.status_code, 413)
        error = response.json()["error"]
        self.assertEqual(error["code"], "REQUEST_TOO_LARGE")
        self.assertIn("request_id", error)

    def test_chunked_body_under_cap_passes_through(self):
        payload = json.dumps(VERIFY_REVIEWED_BODY).encode()

        def chunks():
            for i in range(0, len(payload), 16):
                yield payload[i : i + 16]

        response = self.client.post(
            "/verify-reviewed", content=chunks(), headers={"Content-Type": "application/json"}
        )
        self.assertEqual(response.status_code, 200)

    # --- bearer-token auth -----------------------------------------------------------

    def test_api_token_comparison_accepts_and_rejects(self):
        # Pin behaviour around the constant-time comparison: same-length and
        # different-length wrong tokens both fail, the right one passes.
        with patch.object(security, "API_TOKEN", "s3cret"):
            missing = self.client.post("/verify-reviewed", json=VERIFY_REVIEWED_BODY)
            wrong = self.client.post(
                "/verify-reviewed", json=VERIFY_REVIEWED_BODY, headers={"Authorization": "Bearer s3crex"}
            )
            longer = self.client.post(
                "/verify-reviewed", json=VERIFY_REVIEWED_BODY, headers={"Authorization": "Bearer s3cret-and-more"}
            )
            ok = self.client.post(
                "/verify-reviewed", json=VERIFY_REVIEWED_BODY, headers={"Authorization": "Bearer s3cret"}
            )
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(longer.status_code, 401)
        self.assertEqual(ok.status_code, 200)

    # --- inbound X-Request-ID hygiene ---------------------------------------------------

    def test_inbound_request_id_accepted_when_well_formed(self):
        response = self.client.get("/health", headers={"X-Request-ID": "trace-1.example_42"})
        self.assertEqual(response.headers["x-request-id"], "trace-1.example_42")

    def test_inbound_request_id_regenerated_when_hostile(self):
        # Spaces, path traversal, and oversized values stand in for injection
        # payloads (raw CR/LF never leaves the HTTP client). Each must be
        # replaced with a generated id, exactly as if the header were absent.
        for hostile in ("bad id", "../../etc/passwd", "x" * 65):
            with self.subTest(value=hostile):
                response = self.client.get("/health", headers={"X-Request-ID": hostile})
                generated = response.headers["x-request-id"]
                self.assertNotEqual(generated, hostile)
                self.assertRegex(generated, r"^[0-9a-f]{12}$")

    # --- CSP --------------------------------------------------------------------------------

    def test_csp_allows_blob_frames_for_pdf_preview(self):
        response = self.client.get("/")
        csp = response.headers.get("content-security-policy", "")
        self.assertIn("frame-src 'self' blob:", csp)  # the app.js PDF preview iframe
        self.assertIn("frame-ancestors 'none'", csp)  # embedding US stays forbidden

    # --- Gemini retry budget ---------------------------------------------------------------

    def test_max_attempts_env_below_one_is_clamped(self):
        import app.extraction as extraction

        self.addCleanup(importlib.reload, extraction)  # restore the ambient-env config
        with patch.dict("os.environ", {"GEMINI_MAX_ATTEMPTS": "0"}):
            importlib.reload(extraction)
        self.assertEqual(extraction.MAX_ATTEMPTS, 1)

        calls = {"n": 0}

        def boom(*_a, **_k):
            calls["n"] += 1
            raise RuntimeError("transient")

        with patch("app.extraction._generate_content", side_effect=boom):
            response = self.client.post(
                "/extract",
                data={"product_category": "malt_beverage", "origin_type": "domestic"},
                files={"front_image": ("label.png", PNG_BYTES, "image/png")},
            )
        # A clean 502, not the NameError-driven 500 a zero-iteration loop produced.
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "GEMINI_API_FAILURE")
        self.assertEqual(calls["n"], 1)

    def test_first_attempt_runs_even_with_zero_budget(self):
        import app.extraction as extraction

        calls = {"n": 0}

        def ok(*_a, **_k):
            calls["n"] += 1
            return GeminiResponse(json.dumps({"brand_name": "Example"}))

        with patch("app.extraction._generate_content", side_effect=ok), \
                patch.object(extraction, "GEMINI_DEADLINE_SECONDS", 0.0):
            response = self.client.post(
                "/extract",
                data={"product_category": "malt_beverage", "origin_type": "domestic"},
                files={"front_image": ("label.png", PNG_BYTES, "image/png")},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls["n"], 1)  # the budget gates retries, never attempt 1

    def test_slow_retry_is_cut_off_at_the_remaining_budget(self):
        # A retry that hangs must be abandoned when the wall-clock budget runs
        # out, not allowed to run its full per-call timeout (~12s vs the ~5s bar).
        import app.extraction as extraction

        release = threading.Event()
        # The test loop's shutdown waits for the orphaned worker thread, so park
        # it well past the budget but release it shortly after via a watchdog.
        threading.Timer(0.8, release.set).start()
        self.addCleanup(release.set)
        calls = {"n": 0}

        def fail_fast_then_hang(*_a, **_k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient")
            release.wait(timeout=5)  # parked well past the 0.4s budget
            raise RuntimeError("should have been cut off before this")

        start = time.monotonic()
        with patch("app.extraction._generate_content", side_effect=fail_fast_then_hang), \
                patch.object(extraction, "MAX_ATTEMPTS", 3), \
                patch.object(extraction, "RETRY_BACKOFF_SECONDS", 0.0), \
                patch.object(extraction, "GEMINI_DEADLINE_SECONDS", 0.4):
            response = self.client.post(
                "/extract",
                data={"product_category": "malt_beverage", "origin_type": "domestic"},
                files={"front_image": ("label.png", PNG_BYTES, "image/png")},
            )
        elapsed = time.monotonic() - start

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "GEMINI_API_FAILURE")
        self.assertEqual(calls["n"], 2)  # the hung retry was cut off; no third attempt
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
