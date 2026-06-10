import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class GeminiResponse:
    def __init__(self, text):
        self.text = text


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"
PDF_BYTES = b"%PDF-1.7\n%fake-pdf-body"
OVERSIZED_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + (b"0" * (10 * 1024 * 1024))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

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
        self.assertIn("data-file-slot=\"front\"", response.text)
        self.assertIn("data-drop-slot=\"front\"", response.text)
        self.assertIn("/how-to", response.text)
        self.assertNotIn(">Swagger<", response.text)
        self.assertNotIn("Treasury DOGE</p>", response.text)

    def test_how_to_page_serves(self):
        response = self.client.get("/how-to")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("How To", response.text)
        self.assertIn("Batch upload support is planned next.", response.text)
        self.assertNotIn(">Swagger<", response.text)

    def test_static_app_script_serves(self):
        response = self.client.get("/static/app.js")

        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])
        self.assertIn("field-requirements", response.text)
        self.assertIn("Drop one file per label slot", response.text)

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

    def test_verify_reports_invalid_gemini_json(self):
        with patch("app.extraction._generate_content", return_value=GeminiResponse("[]")):
            response = self.client.post(
                "/verify",
                data={
                    "product_category": "malt_beverage",
                    "origin_type": "domestic",
                    "expected_brand_name": "Example Brewing Co.",
                    "expected_class_type": "Ale",
                    "expected_net_contents": "12 fl oz",
                },
                files={
                    "front_image": ("label.png", PNG_BYTES, "image/png"),
                },
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "GEMINI_INVALID_SCHEMA")


if __name__ == "__main__":
    unittest.main()
