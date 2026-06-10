from fastapi import FastAPI, UploadFile, Form, File
from google import genai
from google.genai import types
from enum import Enum
from dotenv import load_dotenv
from pydantic import BaseModel
import os
import json
import time

load_dotenv()

class ProductCategory(str, Enum):
    malt_beverage = "malt_beverage"
    distilled_spirits = "distilled_spirits"
    wine = "wine"

class OriginType(str, Enum):
    domestic = "domestic"
    imported = "imported"

app = FastAPI()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))



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

For country_of_origin, extract the country of origin statement only if the malt beverage is imported.
Examples:
Product of Germany
Imported from Mexico
Brewed in Belgium
Country of Origin: Ireland
If the label does not show an imported country-of-origin statement, return null.
Do not treat a U.S. city/state as country_of_origin.

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



EXPECTED_WARNING = """
GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects.

(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.
"""



def normalize(value):
    if value is None:
        return ""

    value = value.lower()

    value = value.replace("company", "co")

    value = value.replace("illinois", "il")
    value = value.replace("virginia", "va")

    value = value.replace("sulphites", "sulfites")

    value = value.replace("fluid ounces", "fl oz")
    value = value.replace("fluid ounce", "fl oz")

    value = value.replace("alc/vol", "")
    value = value.replace("abv", "")
    value = value.replace("alcohol by volume", "")
    value = value.replace("alcoholbyvolume", "")

    value = value.replace("produced in", "")
    value = value.replace("product of", "")
    value = value.replace("made in", "")
    value = value.replace("imported from", "")
    value = value.replace("country of origin", "")

    value = value.replace("\n", "")
    value = value.replace(",", "")
    value = value.replace(".", "")
    value = value.replace(":", "")
    value = value.replace("(", "")
    value = value.replace(")", "")
    value = value.replace(" ", "")

    return value.strip()

def check_match(expected, actual): 
    if normalize(expected) == normalize(actual): 
        return "PASS" 
    return "FAIL"

def check_government_warning(actual):
    if not actual:
        return "MISSING"

    normalized_actual = normalize(actual)
    normalized_expected = normalize(EXPECTED_WARNING)

    if normalized_actual == normalized_expected:
        return "PASS"

    if "governmentwarning" not in normalized_actual:
        return "FAIL_MISSING_HEADING"

    return "FAIL_TEXT_MISMATCH"







def validate_fields(expected: dict, reviewed: dict) -> dict:
    return {
        "brand_name": check_match(expected.get("brand_name"), reviewed.get("brand_name")),

        "class_type": check_match(expected.get("class_type"), reviewed.get("class_type")),

        "alcohol_content": (
            check_match(expected.get("alcohol_content"), reviewed.get("alcohol_content"))
            if expected.get("alcohol_content", "").strip()
            else "NOT REQUIRED"
        ),

        "net_contents": check_match(expected.get("net_contents"), reviewed.get("net_contents")),

        "government_warning": check_government_warning(reviewed.get("government_warning")),

        "domestic_name_address": (
            check_match(expected.get("domestic_name_address"), reviewed.get("domestic_name_address"))
            if expected.get("domestic_name_address", "").strip()
            else "NOT REQUIRED"
        ),

        "country_of_origin": (
            check_match(expected.get("country_of_origin"), reviewed.get("country_of_origin"))
            if expected.get("country_of_origin", "").strip()
            else "NOT REQUIRED"
        ),

        "importer_name_address": (
            check_match(expected.get("importer_name_address"), reviewed.get("importer_name_address"))
            if expected.get("importer_name_address", "").strip()
            else "NOT REQUIRED"
        ),

        "sulfite_declaration": (
            check_match(expected.get("sulfite_declaration"), reviewed.get("sulfite_declaration"))
            if expected.get("sulfite_declaration", "").strip()
            else "NOT REQUIRED"
        ),

        "appellation_of_origin": (
            check_match(expected.get("appellation_of_origin"), reviewed.get("appellation_of_origin"))
            if expected.get("appellation_of_origin", "").strip()
            else "NOT REQUIRED"
        ),

        "fanciful_name": (
            check_match(expected.get("fanciful_name"), reviewed.get("fanciful_name"))
            if expected.get("fanciful_name", "").strip()
            else "NOT REQUIRED"
        ),
    }








class LabelFields(BaseModel):
    brand_name: str = ""
    class_type: str = ""
    alcohol_content: str = ""
    net_contents: str = ""
    government_warning: str = ""
    domestic_name_address: str = ""
    importer_name_address: str = ""
    country_of_origin: str = ""
    sulfite_declaration: str = ""
    appellation_of_origin: str = ""
    fanciful_name: str = ""


class VerifyReviewedRequest(BaseModel):
    product_category: ProductCategory
    origin_type: OriginType
    expected: LabelFields
    reviewed: LabelFields






async def extract_label_fields(front_image: UploadFile, back_image: UploadFile | None = None) -> dict:
    front_bytes = await front_image.read()

    contents = [
        EXTRACTION_PROMPT,
        types.Part.from_bytes(
            data=front_bytes,
            mime_type=front_image.content_type
        )
    ]

    if back_image is not None:
        back_bytes = await back_image.read()
        contents.append(
            types.Part.from_bytes(
                data=back_bytes,
                mime_type=back_image.content_type
            )
        )

    last_error = None
    model_name = "gemini-2.5-flash-lite"

    print("USING MODEL:", model_name)

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents
            )
            break
        except Exception as e:
            last_error = e
            time.sleep(5)
    else:
        return {
            "error": "Gemini API failed after 3 attempts",
            "details": str(last_error)
        }

    raw_output = response.text.strip()

    if raw_output.startswith("```json"):
        raw_output = raw_output.replace("```json", "").replace("```", "").strip()
    elif raw_output.startswith("```"):
        raw_output = raw_output.replace("```", "").strip()

    print("RAW GEMINI OUTPUT:", repr(raw_output))

    if not raw_output:
        return {
            "error": "Gemini returned empty output",
            "raw_output": raw_output
        }

    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        return {
            "error": "Gemini did not return valid JSON",
            "raw_output": raw_output
        }



@app.post("/extract")
async def extract(
    product_category: ProductCategory = Form(...),
    origin_type: OriginType = Form(...),
    front_image: UploadFile = File(...),
    back_image: UploadFile | None = File(default=None),
):


    extracted = await extract_label_fields(front_image, back_image)

    return {
    "product_category": product_category.value,
    "origin_type": origin_type.value,
    "extracted": extracted
    }




@app.post("/verify-front")
async def verify_front(
    product_category: ProductCategory = Form(...),
    origin_type: OriginType = Form(...),
    front_image: UploadFile = File(...),
    expected_brand_name: str = Form(...),
    expected_alcohol_content: str = Form(""),
    expected_net_contents: str = Form(...),
    expected_class_type: str = Form(...),
    expected_domestic_name_address: str = Form(""),
    expected_importer_name_address: str = Form(""),
    expected_country_of_origin: str = Form(""),
    expected_sulfite_declaration: str = Form(""),
    expected_appellation_of_origin: str = Form(""),
    expected_fanciful_name: str = Form("")
):
    return await verify(
        product_category=product_category,
        origin_type=origin_type,
        front_image=front_image,
        back_image=None,
        expected_brand_name=expected_brand_name,
        expected_alcohol_content=expected_alcohol_content,
        expected_net_contents=expected_net_contents,
        expected_class_type=expected_class_type,
        expected_domestic_name_address=expected_domestic_name_address,
        expected_importer_name_address=expected_importer_name_address,
        expected_country_of_origin=expected_country_of_origin,
        expected_sulfite_declaration=expected_sulfite_declaration,
        expected_appellation_of_origin=expected_appellation_of_origin,
        expected_fanciful_name=expected_fanciful_name
    )

@app.post("/verify")
async def verify(
    product_category: ProductCategory = Form(...),
    origin_type: OriginType = Form(...),
    front_image: UploadFile = File(...),
    back_image: UploadFile | None = File(default=None),
    expected_brand_name: str = Form(...),
    expected_alcohol_content: str = Form(""),
    expected_net_contents: str = Form(...),
    expected_class_type: str = Form(...),
    expected_domestic_name_address: str = Form(""),
    expected_importer_name_address: str = Form(""),
    expected_country_of_origin: str = Form(""),
    expected_sulfite_declaration: str = Form(""),
    expected_appellation_of_origin: str = Form(""),
    expected_fanciful_name: str = Form("")
):
    
    extracted = await extract_label_fields(front_image, back_image)
    
    category = product_category.value
    origin = origin_type.value

    expected = {
    "brand_name": expected_brand_name,
    "class_type": expected_class_type,
    "alcohol_content": expected_alcohol_content,
    "net_contents": expected_net_contents,
    "domestic_name_address": expected_domestic_name_address,
    "importer_name_address": expected_importer_name_address,
    "country_of_origin": expected_country_of_origin,
    "sulfite_declaration": expected_sulfite_declaration,
    "appellation_of_origin": expected_appellation_of_origin,
    "fanciful_name": expected_fanciful_name,
    }

    validation = validate_fields(expected, extracted)

    return {
    "product_category": category,
    "origin_type": origin,
    "extracted": extracted,
    "validation": validation,
}




@app.post("/verify-reviewed")
async def verify_reviewed(request: VerifyReviewedRequest):
    expected = request.expected.model_dump()
    reviewed = request.reviewed.model_dump()

    validation = validate_fields(expected, reviewed)

    return {
        "product_category": request.product_category.value,
        "origin_type": request.origin_type.value,
        "expected": expected,
        "reviewed": reviewed,
        "validation": validation,
    }

