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

For brand_name, extract ONLY the brand name.
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

For class_type, extract the official Class, Type, or Other Designation exactly as it appears on the label.
Example:
Brand Name: Captain John's
Distinctive/Fanciful Name: Spiced Rum
Class/Type/Other Designation: Rum with Natural Flavors Added

For class_type, extract only text that visibly appears on the label.
Do not infer or create a class/type from nearby words.
Do not turn a fanciful name like "Stormchaser White" into "White Wine."

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

For country_of_origin, return only the country name.
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

For importer_name_address, extract the importer’s company name and city/state only if the malt beverage is imported.
Examples:
Imported by Example Imports LLC, Miami, Florida
Importer: ABC Beverage Imports, Chicago, Illinois
If the label is domestic or does not show importer information, return null.

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
If no sulfite statement appears, return null.
For appellation_of_origin, extract the geographic origin statement for wine if it appears on the label.
Examples:
American
California
Napa Valley
Hudson River Region
Sonoma County
Victoria
France
Bordeaux
Do not use the bottler/importer city and state as appellation_of_origin.
If no wine appellation of origin appears, return null.

For fanciful_name, extract only a true distinctive or fanciful product name.
Do not extract beer styles, class/type designations, beverage categories, or abbreviations as fanciful_name.
Do not extract these as fanciful_name:
Vintage years (e.g. 2007, 2019, any 4-digit year)
Years or numbers that appear as part of a series or vintage
IPA
ALE
LAGER
PILSNER
STOUT
PORTER
HEFEWEIZEN
WHEAT BEER
INDIA PALE ALE
PALE ALE
AMBER ALE
If the label only shows a brand name and a class/type, return null for fanciful_name.
Example:
Brand Name: EXAMPLE BREWING CO.
Class/Type: INDIA PALE ALE
Large decorative text: IPA
fanciful_name: null
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

Return valid JSON only.
Do not use markdown.
Do not wrap the response in triple backticks.

"""
