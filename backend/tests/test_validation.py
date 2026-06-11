import unittest

from app.validation import (
    check_government_warning,
    compute_label_checks,
    get_field_requirements,
    get_wine_path,
    is_approved_standard_of_fill,
    match_alcohol_content,
    match_field,
    match_net_contents,
    net_contents_unit_system,
    normalize_field,
    parse_abv,
    parse_volume,
    validate_distilled_spirits,
    validate_malt_beverage,
    validate_wine,
)


class LabelCheckTests(unittest.TestCase):
    def _find(self, checks, name):
        return next((c for c in checks if c["name"] == name), None)

    def _reviewed(self, **over):
        from app.fields import FIELD_KEYS
        base = {key: "" for key in FIELD_KEYS}
        base.update(over)
        return base

    def test_unit_system_detection(self):
        self.assertEqual(net_contents_unit_system("750 mL"), "metric")
        self.assertEqual(net_contents_unit_system("12 fl oz"), "customary")
        self.assertIsNone(net_contents_unit_system("a bottle"))

    def test_standard_of_fill_membership(self):
        self.assertTrue(is_approved_standard_of_fill("wine", 750))
        self.assertFalse(is_approved_standard_of_fill("wine", 800))
        self.assertTrue(is_approved_standard_of_fill("wine", 5000))  # even-litre >= 4 L
        self.assertTrue(is_approved_standard_of_fill("distilled_spirits", 700))
        self.assertFalse(is_approved_standard_of_fill("distilled_spirits", 740))
        self.assertIsNone(is_approved_standard_of_fill("malt_beverage", 355))

    def test_wine_approved_fill_and_metric(self):
        checks = compute_label_checks("wine", "domestic", self._reviewed(net_contents="750 mL"))
        self.assertEqual(self._find(checks, "net_contents_unit_system")["status"], "PASS")
        self.assertEqual(self._find(checks, "standard_of_fill")["status"], "PASS")

    def test_wine_nonstandard_fill_fails(self):
        checks = compute_label_checks("wine", "domestic", self._reviewed(net_contents="800 mL"))
        self.assertEqual(self._find(checks, "standard_of_fill")["status"], "FAIL")

    def test_wine_wrong_unit_system_fails(self):
        checks = compute_label_checks("wine", "domestic", self._reviewed(net_contents="25 fl oz"))
        self.assertEqual(self._find(checks, "net_contents_unit_system")["status"], "FAIL")

    def test_malt_uses_customary_and_no_fill_check(self):
        checks = compute_label_checks("malt_beverage", "domestic", self._reviewed(net_contents="12 fl oz"))
        self.assertEqual(self._find(checks, "net_contents_unit_system")["status"], "PASS")
        self.assertIsNone(self._find(checks, "standard_of_fill"))

    def test_origin_consistency_imported_with_domestic_address(self):
        checks = compute_label_checks("wine", "imported",
                                      self._reviewed(net_contents="750 mL", domestic_name_address="X, Napa CA"))
        self.assertEqual(self._find(checks, "origin_consistency")["status"], "INFO")


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


class TtbCompletenessTests(unittest.TestCase):
    def _blank(self):
        from app.fields import FIELD_KEYS
        return {key: "" for key in FIELD_KEYS}

    def test_category_scoping_in_requirements(self):
        wine = get_field_requirements("wine", "domestic")
        wine_fields = set(wine["required"] + wine["conditional"] + wine["optional"])
        self.assertIn("grape_varietal", wine_fields)
        self.assertNotIn("statement_of_age", wine_fields)

        malt = get_field_requirements("malt_beverage", "domestic")
        malt_fields = set(malt["required"] + malt["conditional"] + malt["optional"])
        self.assertIn("aspartame_declaration", malt_fields)
        self.assertNotIn("appellation_of_origin", malt_fields)
        self.assertNotIn("vintage_date", malt_fields)

    def test_validation_only_covers_applicable_fields(self):
        validation = validate_wine(self._blank(), self._blank(), "domestic")
        self.assertNotIn("statement_of_age", validation)
        self.assertIn("grape_varietal", validation)

    def test_wine_table_wine_abv_exemption(self):
        reviewed = self._blank()
        reviewed.update(brand_name="X", class_type="Red Table Wine", net_contents="750 ml",
                        domestic_name_address="X, Napa CA")
        validation = validate_wine(self._blank(), reviewed, "domestic")
        self.assertEqual(validation["alcohol_content"], "EXEMPT_TABLE_WINE")

    def test_wine_non_table_missing_abv_when_expected(self):
        expected = self._blank()
        expected.update(alcohol_content="13.5%")
        reviewed = self._blank()
        reviewed.update(brand_name="X", class_type="Chardonnay", net_contents="750 ml")
        validation = validate_wine(expected, reviewed, "domestic")
        self.assertEqual(validation["alcohol_content"], "MISSING")

    def test_appellation_required_by_varietal_trigger(self):
        reviewed = self._blank()
        reviewed.update(brand_name="X", class_type="Cabernet Sauvignon", grape_varietal="Cabernet Sauvignon",
                        vintage_date="2019", net_contents="750 ml", domestic_name_address="X, Napa CA")
        validation = validate_wine(self._blank(), reviewed, "domestic")
        self.assertEqual(validation["appellation_of_origin"], "FAIL_APPELLATION_REQUIRED_BY_TRIGGER")

    def test_appellation_present_passes_when_trigger(self):
        reviewed = self._blank()
        reviewed.update(brand_name="X", class_type="Chardonnay", grape_varietal="Chardonnay",
                        appellation_of_origin="Napa Valley", net_contents="750 ml")
        validation = validate_wine(self._blank(), reviewed, "domestic")
        self.assertEqual(validation["appellation_of_origin"], "PRESENT_ON_LABEL_CONFIRM_APPLICABILITY")

    def test_aspartame_all_caps_format(self):
        bad = self._blank()
        bad.update(brand_name="X", class_type="Ale", net_contents="12 fl oz",
                   aspartame_declaration="Phenylketonurics: Contains Phenylalanine")
        validation = validate_malt_beverage(self._blank(), bad, "domestic")
        self.assertEqual(validation["aspartame_declaration"], "FAIL_NOT_ALLCAPS")

    def test_present_on_label_surfaces_conditional(self):
        reviewed = self._blank()
        reviewed.update(brand_name="X", class_type="Whiskey", alcohol_content="45%", net_contents="750 ml",
                        domestic_name_address="X, Lawrenceburg IN", statement_of_age="Aged 3 Years")
        validation = validate_distilled_spirits(self._blank(), reviewed, "domestic")
        self.assertEqual(validation["statement_of_age"], "PRESENT_ON_LABEL_CONFIRM_APPLICABILITY")


class ComparatorTests(unittest.TestCase):
    # --- text fields: word-boundary, no cross-field corruption ---

    def test_brand_name_phrase_rules_do_not_create_false_pass(self):
        # "made in" is an origin rule; it must not strip a brand name.
        self.assertEqual(match_field("brand_name", "wine", "Made In Heaven", "Heaven"), "FAIL")

    def test_company_fold_is_word_boundary(self):
        # "company" -> "co" must not eat the middle of "Accompany".
        self.assertIn("accompany", normalize_field("brand_name", "Accompany Spirits"))

    def test_distinct_brands_fail(self):
        self.assertEqual(match_field("brand_name", "wine", "Acme Lager", "Zenith Lager"), "FAIL")

    def test_company_and_state_folding_on_address(self):
        self.assertEqual(
            match_field("domestic_name_address", "wine",
                        "Old Town Co., Reston, VA", "Old Town Company Reston Virginia"),
            "PASS",
        )

    def test_state_name_and_abbreviation_match(self):
        self.assertEqual(
            match_field("domestic_name_address", "wine", "Napa, California", "Napa, CA"),
            "PASS",
        )

    def test_country_synonyms_and_lead_phrase(self):
        self.assertEqual(match_field("country_of_origin", "wine", "Product of Australia", "Australia"), "PASS")
        self.assertEqual(match_field("country_of_origin", "wine", "United States", "USA"), "PASS")

    # --- alcohol content: numeric with tolerance ---

    def test_abv_trailing_zero_and_qualifier_match(self):
        self.assertEqual(match_alcohol_content("wine", "13.5%", "13.50%"), "PASS")
        self.assertEqual(match_alcohol_content("wine", "13.5%", "Alc 13.5% by Vol"), "PASS")

    def test_abv_proof_equivalent(self):
        self.assertEqual(match_alcohol_content("distilled_spirits", "40% Alc/Vol", "80 Proof"), "PASS")

    def test_abv_within_and_outside_tolerance(self):
        self.assertEqual(match_alcohol_content("distilled_spirits", "40%", "40.2%"), "PASS")
        self.assertEqual(match_alcohol_content("distilled_spirits", "40%", "41%"), "FAIL")

    def test_abv_gross_mismatch_fails(self):
        self.assertEqual(match_alcohol_content("malt_beverage", "5.5%", "55%"), "FAIL")

    def test_parse_abv_realistic_strings(self):
        self.assertEqual(parse_abv("Alc 13.5% by Vol"), 13.5)
        self.assertEqual(parse_abv("13.5% ABV"), 13.5)
        self.assertEqual(parse_abv("40% Alc/Vol (80 Proof)"), 40.0)
        self.assertIsNone(parse_abv("no numbers here"))

    # --- net contents: unit-aware ---

    def test_net_contents_same_volume_different_unit(self):
        self.assertEqual(match_net_contents("750 ml", "750 mL"), "PASS")
        self.assertEqual(match_net_contents("750 ml", "75 cl"), "PASS")

    def test_net_contents_decimal_not_destroyed(self):
        self.assertEqual(match_net_contents("1.5 L", "15 L"), "FAIL")

    def test_parse_volume(self):
        self.assertEqual(parse_volume("750 ml"), 750.0)
        self.assertEqual(parse_volume("1.5 L"), 1500.0)
        self.assertAlmostEqual(parse_volume("12 fl oz"), 354.882, places=2)

    # --- integration through validate_* ---

    def test_wine_abv_within_tolerance_passes(self):
        validation = validate_wine(
            expected={
                "brand_name": "Example Winery", "class_type": "Chardonnay",
                "alcohol_content": "13.5%", "net_contents": "750 ml",
                "domestic_name_address": "Example Winery, Napa CA",
            },
            reviewed={
                "brand_name": "Example Winery", "class_type": "Chardonnay",
                "alcohol_content": "13.6% Alc/Vol", "net_contents": "750 mL",
                "domestic_name_address": "Example Winery, Napa California",
                "government_warning": "",
            },
            origin_type="domestic",
        )
        self.assertEqual(validation["alcohol_content"], "PASS")
        self.assertEqual(validation["net_contents"], "PASS")
        self.assertEqual(validation["domestic_name_address"], "PASS")


if __name__ == "__main__":
    unittest.main()
