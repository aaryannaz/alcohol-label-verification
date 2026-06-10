import unittest

from app.validation import (
    check_government_warning,
    get_field_requirements,
    get_wine_path,
    parse_abv,
    validate_distilled_spirits,
    validate_malt_beverage,
    validate_wine,
)


class ValidationTests(unittest.TestCase):
    def test_government_warning_accepts_expected_text(self):
        warning = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
            "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
            "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )

        self.assertEqual(check_government_warning(warning), "PASS")

    def test_government_warning_reports_missing_heading(self):
        warning = (
            "(1) According to the Surgeon General, women should not drink alcoholic beverages "
            "during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic "
            "beverages impairs your ability to drive a car or operate machinery, and may cause "
            "health problems."
        )

        self.assertEqual(check_government_warning(warning), "FAIL_MISSING_HEADING")

    def test_government_warning_rejects_title_case_heading(self):
        warning = (
            "Government Warning: (1) According to the Surgeon General, women should not "
            "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
            "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )

        self.assertEqual(check_government_warning(warning), "FAIL_HEADING_FORMAT")

    def test_government_warning_rejects_missing_heading_colon(self):
        warning = (
            "GOVERNMENT WARNING (1) According to the Surgeon General, women should not "
            "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
            "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )

        self.assertEqual(check_government_warning(warning), "FAIL_HEADING_FORMAT")

    def test_government_warning_rejects_punctuation_change(self):
        warning = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General women should not "
            "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
            "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )

        self.assertEqual(check_government_warning(warning), "FAIL_TEXT_MISMATCH")

    def test_government_warning_allows_ocr_line_breaks(self):
        warning = (
            "GOVERNMENT WARNING:\n(1) According to the Surgeon General, women should not\n"
            "drink alcoholic beverages during pregnancy because of the risk of birth defects.\n\n"
            "(2) Consumption of alcoholic beverages impairs your ability to drive a car or\n"
            "operate machinery, and may cause health problems."
        )

        self.assertEqual(check_government_warning(warning), "PASS")

    def test_parse_abv_and_wine_path(self):
        self.assertEqual(parse_abv("13.5%"), 13.5)
        self.assertEqual(get_wine_path("domestic", "6.9%"), "domestic_wine_under_7")
        self.assertEqual(get_wine_path("imported", "13.5%"), "imported_wine_7_or_more")

    def test_malt_beverage_domestic_requirements(self):
        requirements = get_field_requirements("malt_beverage", "domestic")

        self.assertIn("domestic_name_address", requirements["required"])
        self.assertIn("alcohol_content", requirements["conditional"])
        self.assertNotIn("importer_name_address", requirements["required"])
        self.assertNotIn("country_of_origin", requirements["required"])

    def test_malt_beverage_domestic_address_is_required(self):
        validation = validate_malt_beverage(
            expected={
                "brand_name": "Example Brewing Co.",
                "class_type": "Ale",
                "net_contents": "12 fl oz",
                "domestic_name_address": "Example Brewing Co., Chicago IL",
            },
            reviewed={
                "brand_name": "Example Brewing Co.",
                "class_type": "Ale",
                "net_contents": "12 fl oz",
                "domestic_name_address": "",
                "government_warning": "",
            },
            origin_type="domestic",
        )

        self.assertEqual(validation["domestic_name_address"], "MISSING")
        self.assertEqual(validation["alcohol_content"], "NOT REQUIRED")

    def test_malt_beverage_imported_fields_are_required(self):
        validation = validate_malt_beverage(
            expected={
                "brand_name": "Example Lager",
                "class_type": "Imported Beer",
                "net_contents": "12 fl oz",
                "importer_name_address": "Example Imports, Miami FL",
                "country_of_origin": "Mexico",
            },
            reviewed={
                "brand_name": "Example Lager",
                "class_type": "Imported Beer",
                "net_contents": "12 fl oz",
                "importer_name_address": "",
                "country_of_origin": "",
                "government_warning": "",
            },
            origin_type="imported",
        )

        self.assertEqual(validation["importer_name_address"], "MISSING")
        self.assertEqual(validation["country_of_origin"], "MISSING")
        self.assertEqual(validation["domestic_name_address"], "NOT REQUIRED")

    def test_distilled_spirits_alcohol_content_is_required(self):
        validation = validate_distilled_spirits(
            expected={
                "brand_name": "Old Tom Distillery",
                "class_type": "Kentucky Straight Bourbon Whiskey",
                "alcohol_content": "45%",
                "net_contents": "750 ml",
                "domestic_name_address": "Old Tom Distillery, Louisville KY",
            },
            reviewed={
                "brand_name": "Old Tom Distillery",
                "class_type": "Kentucky Straight Bourbon Whiskey",
                "alcohol_content": "",
                "net_contents": "750 ml",
                "domestic_name_address": "Old Tom Distillery, Louisville KY",
                "government_warning": "",
            },
            origin_type="domestic",
        )

        self.assertEqual(validation["alcohol_content"], "MISSING")

    def test_distilled_spirits_imported_fields_are_required(self):
        requirements = get_field_requirements("distilled_spirits", "imported")

        self.assertIn("alcohol_content", requirements["required"])
        self.assertIn("importer_name_address", requirements["required"])
        self.assertIn("country_of_origin", requirements["required"])
        self.assertNotIn("domestic_name_address", requirements["required"])

    def test_wine_domestic_address_is_required(self):
        validation = validate_wine(
            expected={
                "brand_name": "Example Winery",
                "class_type": "Chardonnay",
                "alcohol_content": "13.5%",
                "net_contents": "750 ml",
                "domestic_name_address": "Example Winery, Napa CA",
            },
            reviewed={
                "brand_name": "Example Winery",
                "class_type": "Chardonnay",
                "alcohol_content": "13.5%",
                "net_contents": "750 ml",
                "domestic_name_address": "",
                "government_warning": "",
            },
            origin_type="domestic",
        )

        self.assertEqual(validation["domestic_name_address"], "MISSING")


if __name__ == "__main__":
    unittest.main()
