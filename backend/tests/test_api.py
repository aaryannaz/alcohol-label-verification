import json
import unittest
from unittest.mock import patch

import app.security as security
from app.main import app
from app.schemas import LabelFields
from fastapi.testclient import TestClient


class GeminiResponse:
    def __init__(self, text):
        self.text = text


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"
PDF_BYTES = b"%PDF-1.7\n%fake-pdf-body"
OVERSIZED_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + (b"0" * (10 * 1024 * 1024))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        security._request_log.clear()  # don't let rate-limit state bleed across tests

    def test_field_requirements_endpoint(self):
        response = self.client.get(
            "/field-requirements",
            params={
                "product_category": "distilled_spirits",
                "origin_type": "imported",
            },
        )

        self.assertEqual(response.status_code, 200)
        requirements = response.json()["field_requirements"]
        self.assertIn("alcohol_content", requirements["required"])
        self.assertIn("importer_name_address", requirements["required"])
        self.assertIn("country_of_origin", requirements["required"])

    def test_homepage_serves_minimal_ui(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Alcohol Label Verification", response.text)
        self.assertIn("themeToggle", response.text)
        self.assertIn("layoutSelect", response.text)
        self.assertIn("data-file-slot=\"front\"", response.text)
        self.assertIn("data-drop-slot=\"front\"", response.text)
        self.assertIn("modeBatch", response.text)
        self.assertIn("id=\"batchPanel\"", response.text)
        self.assertIn("batchDropZone", response.text)
        self.assertIn("processBatchButton", response.text)
        self.assertIn("/how-to", response.text)
        self.assertNotIn("github.com", response.text)
        self.assertNotIn(">Swagger<", response.text)
        self.assertNotIn("Treasury DOGE</p>", response.text)

    def test_how_to_page_serves(self):
        response = self.client.get("/how-to")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("How To", response.text)
        self.assertIn("Each batch file is treated as one review item.", response.text)
        self.assertIn("Use Batch mode when uploading multiple review items at once.", response.text)
        self.assertIn("CSV or Excel import is a future enhancement.", response.text)
        self.assertNotIn(">Swagger<", response.text)

    def test_static_app_script_serves(self):
        response = self.client.get("/static/app.js")

        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])
        self.assertIn("field-requirements", response.text)
        self.assertIn("setUploadMode(\"batch\")", response.text)
        self.assertIn("Use Batch for multiple files", response.text)
        self.assertIn("processBatchQueue", response.text)

    def test_verify_reviewed_includes_field_requirements(self):
        response = self.client.post(
            "/verify-reviewed",
            json={
                "product_category": "malt_beverage",
                "origin_type": "domestic",
                "expected": {
                    "brand_name": "Example Brewing Co.",
                    "class_type": "Ale",
                    "net_contents": "12 fl oz",
                    "domestic_name_address": "Example Brewing Co., Chicago IL",
                },
                "reviewed": {
                    "brand_name": "Example Brewing Co.",
                    "class_type": "Ale",
                    "net_contents": "12 fl oz",
                    "domestic_name_address": "Example Brewing Co., Chicago IL",
                    "government_warning": "",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("field_requirements", body)
        self.assertIn("domestic_name_address", body["field_requirements"]["required"])
        self.assertEqual(body["validation"]["alcohol_content"], "NOT REQUIRED")

    def test_extract_rejects_unsupported_file_type(self):
        response = self.client.post(
            "/extract",
            data={
                "product_category": "malt_beverage",
                "origin_type": "domestic",
            },
            files={
                "front_image": ("label.txt", b"not an image", "text/plain"),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "UNSUPPORTED_FILE_EXTENSION")

    def test_extract_rejects_content_type_mismatch(self):
        response = self.client.post(
            "/extract",
            data={
                "product_category": "malt_beverage",
                "origin_type": "domestic",
            },
            files={
                "front_image": ("label.png", PNG_BYTES, "application/pdf"),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "UNSUPPORTED_FILE_TYPE")

    def test_extract_rejects_invalid_file_signature(self):
        response = self.client.post(
            "/extract",
            data={
                "product_category": "malt_beverage",
                "origin_type": "domestic",
            },
            files={
                "front_image": ("label.png", b"not really a png", "image/png"),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_FILE_SIGNATURE")

    def test_extract_rejects_empty_upload(self):
        response = self.client.post(
            "/extract",
            data={
                "product_category": "malt_beverage",
                "origin_type": "domestic",
            },
            files={
                "front_image": ("label.png", b"", "image/png"),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "EMPTY_UPLOAD")

    def test_extract_rejects_oversized_upload(self):
        response = self.client.post(
            "/extract",
            data={
                "product_category": "malt_beverage",
                "origin_type": "domestic",
            },
            files={
                "front_image": ("label.png", OVERSIZED_PNG_BYTES, "image/png"),
            },
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "UPLOAD_TOO_LARGE")

    def test_extract_validates_back_image(self):
        response = self.client.post(
            "/extract",
            data={
                "product_category": "malt_beverage",
                "origin_type": "domestic",
            },
            files={
                "front_image": ("front.png", PNG_BYTES, "image/png"),
                "back_image": ("back.txt", b"not an image", "text/plain"),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["details"]["field"], "back_image")

    def test_extract_reports_invalid_gemini_json(self):
        with patch("app.extraction._generate_content", return_value=GeminiResponse("not json")):
            response = self.client.post(
                "/extract",
                data={
                    "product_category": "malt_beverage",
                    "origin_type": "domestic",
                },
                files={
                    "front_image": ("label.png", PNG_BYTES, "image/png"),
                },
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "GEMINI_INVALID_JSON")

    def test_extract_reports_invalid_gemini_schema(self):
        with patch("app.extraction._generate_content", return_value=GeminiResponse("[]")):
            response = self.client.post(
                "/extract",
                data={
                    "product_category": "malt_beverage",
                    "origin_type": "domestic",
                },
                files={
                    "front_image": ("label.png", PNG_BYTES, "image/png"),
                },
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "GEMINI_INVALID_SCHEMA")

    def test_extract_happy_path_coerces_fields(self):
        model_output = {
            "brand_name": "Example Brewing Co.",
            "class_type": "Imported Beer",
            "government_warning": None,
            "hallucinated_field": "should be dropped",
        }

        with patch(
            "app.extraction._generate_content",
            return_value=GeminiResponse(json.dumps(model_output)),
        ):
            response = self.client.post(
                "/extract",
                data={"product_category": "malt_beverage", "origin_type": "imported"},
                files={"front_image": ("label.png", PNG_BYTES, "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        extracted = response.json()["extracted"]
        # Exactly the LabelFields key set — no hallucinated keys leak through.
        self.assertEqual(set(extracted), set(LabelFields.model_fields))
        # Leading "Imported " is stripped from class_type.
        self.assertEqual(extracted["class_type"], "Beer")
        # null / missing fields are coerced to "".
        self.assertEqual(extracted["government_warning"], "")
        self.assertEqual(extracted["fanciful_name"], "")

    def test_extract_coerces_nullish_string_literals_to_empty(self):
        model_output = {
            "brand_name": "Example Winery",
            "importer_name_address": "null",
            "sulfite_declaration": "N/A",
            "appellation_of_origin": "None",
        }

        with patch(
            "app.extraction._generate_content",
            return_value=GeminiResponse(json.dumps(model_output)),
        ):
            response = self.client.post(
                "/extract",
                data={"product_category": "wine", "origin_type": "domestic"},
                files={"front_image": ("label.png", PNG_BYTES, "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        extracted = response.json()["extracted"]
        self.assertEqual(extracted["importer_name_address"], "")
        self.assertEqual(extracted["sulfite_declaration"], "")
        self.assertEqual(extracted["appellation_of_origin"], "")
        self.assertEqual(extracted["brand_name"], "Example Winery")

    def test_extract_error_details_do_not_leak_raw_model_output(self):
        with patch(
            "app.extraction._generate_content",
            return_value=GeminiResponse("Here is the JSON you asked for"),
        ):
            response = self.client.post(
                "/extract",
                data={"product_category": "malt_beverage", "origin_type": "domestic"},
                files={"front_image": ("label.png", PNG_BYTES, "image/png")},
            )

        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertEqual(body["error"]["code"], "GEMINI_INVALID_JSON")
        # The raw model text must not be echoed back to the client.
        self.assertEqual(body["error"]["details"], {})


    def test_fields_endpoint_matches_label_fields(self):
        response = self.client.get("/fields")
        self.assertEqual(response.status_code, 200)
        specs = response.json()["fields"]
        keys = [spec["key"] for spec in specs]
        # /fields, LabelFields, and validation.FIELD_ORDER all derive from one source.
        self.assertEqual(keys, list(LabelFields.model_fields))
        from app.validation import FIELD_ORDER
        self.assertEqual(tuple(keys), tuple(FIELD_ORDER))
        for spec in specs:
            self.assertIn(spec["control"], {"text", "textarea"})
            self.assertTrue(spec["label"])

    def test_verify_reviewed_includes_compliance_checks(self):
        response = self.client.post(
            "/verify-reviewed",
            json={
                "product_category": "wine",
                "origin_type": "domestic",
                "expected": {"brand_name": "X", "class_type": "Chardonnay", "net_contents": "800 ml"},
                "reviewed": {"brand_name": "X", "class_type": "Chardonnay", "net_contents": "800 ml"},
            },
        )
        self.assertEqual(response.status_code, 200)
        checks = response.json()["compliance_checks"]
        names = {c["name"]: c["status"] for c in checks}
        # 800 mL is not an approved wine standard of fill.
        self.assertEqual(names.get("standard_of_fill"), "FAIL")

    def test_removed_legacy_verify_endpoints_are_gone(self):
        # The dead flat-form endpoints were deleted in favor of /verify-reviewed.
        self.assertEqual(self.client.post("/verify").status_code, 404)
        self.assertEqual(self.client.post("/verify-front").status_code, 404)

    def test_request_validation_uses_error_envelope(self):
        response = self.client.get(
            "/field-requirements",
            params={"product_category": "bogus", "origin_type": "domestic"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")

    def test_unhandled_error_uses_error_envelope(self):
        client = TestClient(app, raise_server_exceptions=False)
        body = {"product_category": "wine", "origin_type": "domestic", "expected": {}, "reviewed": {}}
        with patch("app.main.validate_label_fields", side_effect=RuntimeError("boom")):
            response = client.post("/verify-reviewed", json=body)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "INTERNAL_ERROR")
        # Internal error text is not leaked to the client.
        self.assertEqual(response.json()["error"]["details"], {})

    def test_request_id_header_and_error_correlation(self):
        ok = self.client.get("/health")
        self.assertTrue(ok.headers.get("x-request-id"))
        err = self.client.get(
            "/field-requirements", params={"product_category": "bad", "origin_type": "domestic"}
        )
        self.assertEqual(err.status_code, 422)
        self.assertTrue(err.headers.get("x-request-id"))
        self.assertIn("request_id", err.json()["error"])

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readyz_ready_when_key_present(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "x"}):
            response = self.client.get("/readyz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")

    def test_readyz_not_ready_when_key_absent(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            response = self.client.get("/readyz")
        self.assertEqual(response.status_code, 503)

    def test_security_headers_present(self):
        response = self.client.get("/")
        self.assertIn("default-src 'self'", response.headers.get("content-security-policy", ""))
        self.assertEqual(response.headers.get("x-frame-options"), "DENY")
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(response.headers.get("referrer-policy"), "no-referrer")

    def test_rate_limit_blocks_after_threshold(self):
        body = {"product_category": "wine", "origin_type": "domestic", "expected": {}, "reviewed": {}}
        with patch.object(security, "RATE_LIMIT_REQUESTS", 2):
            codes = [self.client.post("/verify-reviewed", json=body).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_api_token_required_when_configured(self):
        body = {"product_category": "wine", "origin_type": "domestic", "expected": {}, "reviewed": {}}
        with patch.object(security, "API_TOKEN", "s3cret"):
            no_token = self.client.post("/verify-reviewed", json=body)
            wrong = self.client.post("/verify-reviewed", json=body, headers={"Authorization": "Bearer nope"})
            ok = self.client.post("/verify-reviewed", json=body, headers={"Authorization": "Bearer s3cret"})
        self.assertEqual(no_token.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(ok.status_code, 200)

    def test_oversized_request_body_rejected(self):
        body = {"product_category": "wine", "origin_type": "domestic", "expected": {}, "reviewed": {}}
        with patch.object(security, "MAX_REQUEST_BYTES", 10):
            response = self.client.post("/verify-reviewed", json=body)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "REQUEST_TOO_LARGE")


if __name__ == "__main__":
    unittest.main()
