EXTRACTION_PROMPT = """
Analyze the uploaded alcohol image or images.
If two images are provided, the first is the front label and the second is the back label.
If only one image is provided, extract as much as possible from that image.

Extract:
- brand_name
- class_type
- alcohol_content
- net_contents
- government_warning
- domestic_name_address
- importer_name_address
- country_of_origin
- sulfite_declaration
- appellation_of_origin
- fanciful_name
- fdc_yellow_5_declaration
- cochineal_carmine_declaration
- aspartame_declaration
- statement_of_age
- commodity_statement
- coloring_materials
- wood_treatment
- state_of_distillation
- vintage_date
- grape_varietal
- percentage_of_foreign_wine

If a specific field does not appear on the label, return an empty string for that field. This applies to absent disclosures and statements — but you must still extract a genuine fanciful/distinctive product name when one is present (see the fanciful_name rules below); a real fanciful name is not an "inferred" value.

For brand_name, extract the COMPLETE brand name exactly as it is printed in the brand block.
Do not combine brand names with class/type designations, beverage categories, or flavor descriptions.
But a brand name is often MORE than one word, and you must NOT truncate it.

CRITICAL brand_name rule — do NOT drop the last word.
Trailing brand descriptors that are visually part of the same brand block are PART of brand_name. These include:
- a series word: Series
- a tier/quality word that is part of the brand identity: Reserve
- a place word that is part of the brand identity: Highland
- a name-number that is part of the brand identity: a number like 13 or a date like 1842 printed as part of the name
When the brand block ends in one of these, keep the WHOLE brand name. Never drop the final token.

Corrected brand_name examples (left = what is printed, right = correct output):
- "Wandering Roots Series" -> WANDERING ROOTS SERIES   (NOT "WANDERING ROOTS" — keep "Series")
- "EDELWEISS RESERVE" -> EDELWEISS RESERVE             (NOT "EDELWEISS" — keep "RESERVE")
- "Stillhouse 13" -> STILLHOUSE 13                     (NOT "STILLHOUSE" — keep the number "13")
- "Glenmorrow Highland Reserve" -> GLENMORROW HIGHLAND RESERVE   (NOT "GLENMORROW")
- "Chateau Margaux Reserve" -> CHATEAU MARGAUX RESERVE   (NOT "CHATEAU MARGAUX")
- "EASTLINE BREWING 1842" -> EASTLINE BREWING 1842      (NOT "EASTLINE BREWING" — 1842 is part of the brand, not a vintage)

The ONLY exception: a true separate wine VINTAGE year (for example a "2020" printed by itself as the harvest/vintage year on a wine) is NOT part of brand_name. A name-number that is part of the brand identity (like "13" or "1842" above) IS part of brand_name. Use the layout to decide: a year printed as its own standalone vintage line is a vintage; a number printed inside the brand name block is part of the brand.

For brand_name, extract ONLY the brand name, not the product/fanciful name.
Example:
Brand Name = Captain John's
NOT Captain John's Spiced Rum
Do not combine brand names with product names,
fanciful names, class/type designations,
or flavor descriptions.

For beer labels, distinguish these fields:
Brand Name = the company, brand, series, or product-line name under which the beverage is sold.
Distinctive/Fanciful Name = a creative product name, pun, seasonal name, or flavor name.
Class/Type/Other Designation  = the official product type or composition statement.
Do not use the distinctive/fanciful name as brand_name.
Example:
Brand Name: Example Brewing Company
Distinctive/Fanciful Name: Happy Elder After
Class/Type/Other Designation: Ale with Elderberries
NOT Brand Name: Happily Elder After

For beer labels, do not assume the brewery name is the brand name.
The brand name may be a series name or a product-line name.
Example:
Brewery/producer name: Malt & Hop Brewery
Brand Name: Farm To Table Series #1
Distinctive/Fanciful Name: Honey Huckleberry Pie
Class/Type/Other Designation: Ale with Honey and Huckleberry Flavor
For this example, brand_name must be Farm To Table Series #1, not Malt & Hop

For class_type, extract the FULL official Class, Type, or Other Designation exactly as it appears on the label.
Include ALL leading and embedded modifiers that are part of the official designation. Do not shorten it to the bare beverage category.
Keep these as part of class_type:
- leading style modifiers (e.g. "Hazy", "Reposado")
- semi-generic geographic qualifiers that precede the type (e.g. "California" in "California Chablis")
- full composition statements (e.g. "Brewed with Cherries", "Ale Brewed with Cherries")

Corrected class_type examples (left = printed designation, right = correct output):
- "Hazy India Pale Ale" -> Hazy India Pale Ale          (NOT "India Pale Ale" — keep "Hazy")
- "Ale Brewed with Cherries" -> Ale Brewed with Cherries (NOT "Ale" — keep the composition statement)
- "Reposado Tequila" -> Reposado Tequila                (NOT "Tequila" — keep "Reposado")
- "California Chablis" -> California Chablis             (NOT "Chablis" — keep the semi-generic qualifier "California")

Example:
Brand Name: Captain John's
Distinctive/Fanciful Name: Spiced Rum
Class/Type/Other Designation: Rum with Natural Flavors Added

For class_type, do not include the word "Imported" or "Domestic" as part of the class/type designation. These describe origin, not class/type. (Note: "Imported"/"Domestic" are the only words you strip — keep every other modifier such as Hazy, Reposado, or California.)
Examples:
Imported Beer -> Beer
Imported Ale -> Ale
Imported Reposado Tequila -> Reposado Tequila

For class_type, extract only text that visibly appears on the label.
Do not infer or create a class/type from nearby words.
Do not turn a fanciful name like "Stormchaser White" into "White Wine."
Do not split a fanciful name — if the fanciful name contains a color word like White, Red, or Rosé, keep the full name together.
Example:
Fanciful name on label: STORMCHASER WHITE
fanciful_name: Stormchaser White
NOT fanciful_name: Stormchaser

For alcohol_content, extract ONLY the alcohol by volume percentage.
Examples:
20%
13.5%
5%
Do not include:
Alcohol By Volume
Proof
ABV

Do not use IPA, Ale, Beer, Lager, Wine, Rum, Vodka, Whiskey, or other class/type words as brand_name.
If a large text item is a class/type, product style, or abbreviation like IPA, do not treat it as the brand name.
Example:
Brand Name: Example Brewing Co.
Class/Type: India Pale Ale
NOT Brand Name: IPA

For domestic_name_address, extract the company name together with the city and state that satisfy the Name and Address requirement.
It is possible for the company (Name) to be the same as the brand name in some cases.
Examples:
EXAMPLE BREWING CO.
ARLINGTON VIRGINIA
domestic_name_address:
EXAMPLE BREWING CO., ARLINGTON VIRGINIA
Brewed and Bottled by Example Brewing Co.
Arlington, Virginia
domestic_name_address:
Example Brewing Co., Arlington Virginia
Examples:
"Brewed and Bottled by Example Brewing Company, Chicago, Illinois"
"Bottled by Captain John's Distilling Co., Louisville, Kentucky"
"Imported by Example Imports LLC, Miami, Florida"
Return the complete statement exactly as it appears.

domestic_name_address applies ONLY to DOMESTIC products.
If the product is IMPORTED, domestic_name_address must be an empty string, even if a foreign distillery, brewery, or winery is shown on the label. A foreign producer address on an imported product does NOT go in domestic_name_address — the responsible U.S. party goes in importer_name_address instead.
Example:
Imported product. Label shows "Distilled by Glen Foreign Distillery, Speyside, Scotland" and "Imported by Example Imports LLC, Miami, Florida".
domestic_name_address: (empty string)
importer_name_address: Example Imports LLC, Miami, Florida

For domestic_name_address, extract only:
Company Name, City, State
Do not include explanatory phrases such as:
Brewed By
Bottled By
Brewed and Bottled By
Produced By
Produced and Bottled By
Packed By

For domestic_name_address, extract the bottler's name and address (city and state) that satisfy the TTB Name and Address requirement.
The bottler's name may be:
- the same as the brand name
- different from the brand name
- a brewer, bottler, packer, or producer depending on the label
If the label shows only one company name `together` with a city and state, and no other responsible party is identified, treat that company as the bottler for purposes of domestic_name_address extraction.
The domestic_name_address field must contain BOTH:
1. the bottler name
2. the city and state
Incorrect:
ARLINGTON VIRGINIA
Correct:
EXAMPLE BREWING CO., ARLINGTON VIRGINIA
Example:
Brand Name:
EXAMPLE BREWING CO.
Location:
ARLINGTON VIRGINIA
Output:
domestic_name_address:
EXAMPLE BREWING CO., ARLINGTON VIRGINIA
Do not return only the city and state.

For country_of_origin, return only the COUNTRY name. It must be a country, never a state, region, or appellation.
Examples:
Product of Australia -> AUSTRALIA
Imported from Mexico -> MEXICO
Brewed in Belgium -> BELGIUM
Country of Origin: Ireland -> IRELAND
Do not include phrases such as:
Product of
Imported from
Brewed in
Country of Origin
Do NOT put a U.S. state (for example "California") in country_of_origin. A state is not a country.
For a DOMESTIC product, country_of_origin is an empty string.

For importer_name_address, extract the importer’s company name and city/state only if the malt beverage is imported.
Examples:
Imported by Example Imports LLC, Miami, Florida
Importer: ABC Beverage Imports, Chicago, Illinois
If the label is domestic or does not show importer information, return an empty string.

For importer_name_address, extract only:
Importer Company Name, City, State
Do not include:
Imported By
Sole Agent
Sole U.S. Agent

For imported malt beverages, do not use importer_name_address as brand_name unless the importer is clearly also the brand name.
If the label has a beer style or product name shown prominently, and a separate "Imported by" company appears elsewhere, the "Imported by" company should go in importer_name_address, not brand_name.
Example:
Front label: HEFEWEIZEN
Imported by: Malt & Hop Brewery, Hyattsville, Maryland
brand_name: Hefeweizen
class_type: Imported Beer
importer_name_address: Malt & Hop Brewery, Hyattsville, Maryland

For sulfite_declaration, extract the sulfite statement only if it appears on the label.
Examples:
Contains Sulfites
Contains Sulphites
Contains sulfur dioxide
If no sulfite statement appears, return an empty string.

For appellation_of_origin, extract the geographic origin statement for WINE only, if it appears on the label.
Examples:
American
California
Napa Valley
Hudson River Region
Sonoma County
Victoria
France
Bordeaux
appellation_of_origin is a WINE field ONLY. Do NOT use it for spirits or beer.
Do NOT put a spirits region (for example "Speyside", "Highland", "Islay", "Cognac" as a region) in appellation_of_origin.
Do not use the bottler/importer city and state as appellation_of_origin.
If no wine appellation of origin appears, return an empty string.

For fanciful_name, extract ONLY a genuinely distinctive or fanciful product name — a creative coined name, a pun, or an evocative phrase that is uniquely the product's own name.
DEFAULT TO AN EMPTY STRING. If you are not confident the text is a true creative product name, return "".

fanciful_name must NEVER be any of the following (these are FORBIDDEN — return "" instead):
- a quality/tier word such as Reserve, Reserva, Special Reserve, Premium, Select
- any number (for example 13)
- any vintage or year (for example 2020, "Vintage 2020", or any 4-digit year)
- any style or class/type word (for example Hefeweizen, Reposado, IPA, Ale, Lager, Pilsner, Stout, Porter, India Pale Ale, Pale Ale, Amber Ale, Wheat Beer)
- any fragment or trailing word that was split off the brand name (for example "Series", "Highland", or the last word you were tempted to drop from the brand)

Forbidden -> correct fanciful_name examples (each should be empty):
- "RESERVE" -> ""                 (it is a tier word, and it belongs in brand_name, e.g. EDELWEISS RESERVE)
- "13" -> ""                      (a number; it belongs in brand_name, e.g. STILLHOUSE 13)
- "Reposado" -> ""                (a style word; it belongs in class_type, e.g. Reposado Tequila)
- "Highland Reserve" -> ""        (a fragment of the brand; it belongs in brand_name, e.g. GLENMORROW HIGHLAND RESERVE)
- "Vintage 2020" -> ""            (a vintage/year)
- "HefeWeizen" -> ""              (a style word; it belongs in class_type)

However, do NOT over-suppress: a genuine creative product name IS the fanciful_name. When a line of text is neither the brand, nor a bare style/category, nor a tier/number/vintage, and it reads like the product's own distinctive name (a flavor-based name, a coined name, an evocative phrase), extract it.
DO extract these as fanciful_name:
- "Spiced Rum" -> Spiced Rum                 (a distinctive product name between the brand "Captain John's" and the class/type "Rum with Natural Flavors Added")
- "Stormchaser White" -> Stormchaser White   (an evocative product name; keep the color word "White" attached)
- "Hazy Days Ahead" -> Hazy Days Ahead        (a pun, distinct from the "Hazy India Pale Ale" class/type)
- "Midnight Abbey" -> Midnight Abbey          (a coined product name)
The distinction: "Spiced Rum" is the product's own flavor-based name (fanciful), but a bare "Reposado" or "Hefeweizen" by itself is only a style word (not fanciful).

Do not extract beer styles, class/type designations, beverage categories, or abbreviations as fanciful_name.
If the label only shows a brand name and a class/type, return an empty string for fanciful_name.
Example:
Brand Name: EXAMPLE BREWING CO.
Class/Type: INDIA PALE ALE
Large decorative text: IPA
fanciful_name: (leave empty)
Example:
Brand Name: EXAMPLE BREWING CO.
Class/Type: ALE WITH ELDERBERRIES
Distinctive/Fanciful Name: HAPPY ELDER AFTER
fanciful_name: HAPPY ELDER AFTER

If the brand name appears across multiple stacked lines, combine the stacked lines.
Example:
12345
IMPORTS
brand_name:
12345 IMPORTS
Do not omit a smaller word if it is visually part of the same brand block.
If the front label shows a shortened or stacked brand name, and the back label identifies the same entity more completely, use the complete entity name as brand_name.
Example:
Front: 12345
Back: Imported by 12345 Imports
brand_name: 12345 IMPORTS

For government_warning, include the heading "GOVERNMENT WARNING:" if it appears on the label.
Do not omit the heading.
Extract the full warning statement, including the heading and both numbered sentences.

Carefully scan the ENTIRE label — including small print, side text, and the back label — for each of the following disclosure statements. They are easy to overlook but must be captured verbatim when present.

For fdc_yellow_5_declaration, extract the FD&C Yellow #5 disclosure only if it appears, e.g. "Contains FD&C Yellow #5". Return it exactly as printed (keep "FD&C" and "#5"). Do not infer it from a generic "artificially colored" phrase that does not name Yellow #5. Otherwise return an empty string.

For cochineal_carmine_declaration, extract the cochineal extract / carmine disclosure only if it appears, e.g. "Contains Carmine" or "Contains Cochineal Extract". Return it exactly as printed. Otherwise return an empty string.

For aspartame_declaration, extract the aspartame disclosure only if it appears. The required wording is "PHENYLKETONURICS: CONTAINS PHENYLALANINE." Return it EXACTLY as printed, preserving its capitalization (do not change the case yourself). Otherwise return an empty string.

For statement_of_age, extract an age statement only if an age claim appears, e.g. "3 Years Old", "Aged not less than 6 months", or a blended form "40% whisky aged 5 years; 60% whisky aged 8 years". Capture the full age phrase including the number and unit. Otherwise return an empty string.

For commodity_statement, extract a neutral-spirits commodity statement only if it appears, e.g. "50% Neutral Spirits Distilled From Corn" or "Distilled from Grain". Return the full statement as printed. Otherwise return an empty string.

For coloring_materials, extract a coloring-materials disclosure only if it appears, e.g. "Colored With Caramel", "Artificially Colored", "Certified Color Added". Return the full disclosure as printed. Otherwise return an empty string.

For wood_treatment, extract a wood-treatment statement only if it appears, e.g. "Colored and flavored with wood chips". Return the full statement as printed. Otherwise return an empty string.

For state_of_distillation, extract a state of distillation ONLY from an explicit "Distilled in <State>" phrasing, e.g. "Distilled in Idaho" -> "Idaho". Return just the U.S. state name. Do NOT infer it from a class/type like "Tennessee Whiskey" or "Kentucky Bourbon". Otherwise return an empty string.

For vintage_date, extract a wine harvest/vintage year ONLY if a year is printed as its own statement, e.g. "Vintage 2020" -> "2020", "2019" -> "2019". Return ONLY the 4-digit year, with no surrounding words. A vintage year is NOT a fanciful name and is NOT part of the brand. Otherwise return an empty string.

For grape_varietal, extract the grape varietal name(s) used to designate the wine, if printed, e.g. "Cabernet Sauvignon", "Chardonnay". If two or more varietals are listed, return them comma-separated in printed order. Otherwise return an empty string. IMPORTANT: when a wine's type designation IS its grape varietal (e.g. a wine labeled simply "Chardonnay" or "Cabernet Sauvignon"), that varietal is BOTH the class_type AND the grape_varietal — put it in both fields, do not leave class_type empty.

For percentage_of_foreign_wine, extract the American-vs-foreign-wine percentage statement only if it appears, e.g. "50% American wine/50% French wine". Return the statement as printed including the percentage figures. Otherwise return an empty string.

REMINDER before you answer: re-check fanciful_name. If the label shows a genuine distinctive/creative product name (a flavor-based name, a coined name, a pun, an evocative phrase) that is separate from the brand and the class/type — for example "Spiced Rum", "Midnight Abbey", "Hazy Days Ahead", "Stormchaser White", "Midnight Frost" — you MUST put it in fanciful_name. Do not leave fanciful_name empty when such a name is present.

Return valid JSON only.
Do not use markdown.
Do not wrap the response in triple backticks.
"""
