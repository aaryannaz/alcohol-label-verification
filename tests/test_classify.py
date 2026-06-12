import unittest

from app.classify import classify_category, classify_origin


class ClassifyCategoryTests(unittest.TestCase):
    def test_category_from_class_type(self):
        self.assertEqual(classify_category({"class_type": "Hazy India Pale Ale"}), "malt_beverage")
        self.assertEqual(classify_category({"class_type": "Amber Lager"}), "malt_beverage")
        self.assertEqual(classify_category({"class_type": "Tart Ale with Boysenberry"}), "malt_beverage")
        self.assertEqual(classify_category({"class_type": "IPA"}), "malt_beverage")
        self.assertEqual(classify_category({"class_type": "Cabernet Sauvignon"}), "wine")
        self.assertEqual(classify_category({"class_type": "California Chablis"}), "wine")
        self.assertEqual(classify_category({"class_type": "Red Table Wine"}), "wine")
        self.assertEqual(classify_category({"class_type": "Kentucky Straight Bourbon Whiskey"}), "distilled_spirits")
        self.assertEqual(classify_category({"class_type": "Reposado Tequila"}), "distilled_spirits")
        self.assertEqual(classify_category({"class_type": "London Dry Gin"}), "distilled_spirits")

    def test_keywords_match_whole_words_only(self):
        # Substring matching misclassified these: "Porter" contains "port"
        # (wine), "Export" contains "port", "Ginger"/"Virginia" contain "gin".
        self.assertEqual(classify_category({"class_type": "Porter"}), "malt_beverage")
        self.assertEqual(classify_category({"class_type": "Robust Porter"}), "malt_beverage")
        self.assertEqual(classify_category({"class_type": "Export Lager"}), "malt_beverage")
        self.assertEqual(classify_category({"class_type": "Ginger Beer"}), "malt_beverage")
        self.assertEqual(classify_category({"class_type": "Virginia Lager"}), "malt_beverage")

    def test_rightmost_keyword_wins_on_mixed_designations(self):
        # TTB class/type designations end with the class noun: a "Rye Ale" is
        # an ale and a "Bourbon Barrel Stout" is a stout, despite the spirits
        # words earlier in the string.
        self.assertEqual(classify_category({"class_type": "Rye Ale"}), "malt_beverage")
        self.assertEqual(classify_category({"class_type": "Bourbon Barrel Stout"}), "malt_beverage")
        # ...and the converse: the trailing class noun is the spirit.
        self.assertEqual(classify_category({"class_type": "Malt Whiskey"}), "distilled_spirits")

    def test_unicode_word_boundary_matches_rose(self):
        # \b is Unicode-aware in Python 3 str regexes, so the accented keyword
        # matches as a whole word.
        self.assertEqual(classify_category({"class_type": "Rosé"}), "wine")
        self.assertEqual(classify_category({"class_type": "Sparkling Rosé"}), "wine")

    def test_class_type_outranks_fanciful_name(self):
        # The fanciful name is a fallback only — a spirits-flavored fanciful
        # name must not override a malt class/type.
        fields = {"class_type": "Stout", "fanciful_name": "Bourbon Dreams"}
        self.assertEqual(classify_category(fields), "malt_beverage")

    def test_fanciful_name_used_when_class_type_yields_nothing(self):
        fields = {"class_type": "", "fanciful_name": "Cabernet Reserve"}
        self.assertEqual(classify_category(fields), "wine")

    def test_category_defaults_to_malt_when_unknown(self):
        self.assertEqual(classify_category({"class_type": ""}), "malt_beverage")
        self.assertEqual(classify_category({}), "malt_beverage")


class ClassifyOriginTests(unittest.TestCase):
    def test_origin_imported_when_importer_or_country(self):
        self.assertEqual(classify_origin({"importer_name_address": "Acme Imports, NY"}), "imported")
        self.assertEqual(classify_origin({"country_of_origin": "Germany"}), "imported")

    def test_origin_domestic_when_only_bottler(self):
        self.assertEqual(classify_origin({"domestic_name_address": "Bluebird, PA"}), "domestic")


if __name__ == "__main__":
    unittest.main()
