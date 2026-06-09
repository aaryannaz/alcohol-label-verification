from fastapi import FastAPI, UploadFile, Form
from openai import OpenAI
from dotenv import load_dotenv
import os
import base64
import json

load_dotenv()

app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def normalize(value):
    if value is None:
        return ""
    return value.lower().replace(" ", "").replace(".", "").strip()

def check_match(expected, actual):
    if normalize(expected) == normalize(actual):
        return "PASS"
    return "FAIL"

@app.post("/verify")
async def verify(
    front_image: UploadFile,
    back_image: UploadFile,
    expected_brand_name: str = Form(...),
    expected_alcohol_content: str = Form(...),
    expected_net_contents: str = Form(...),
    expected_class_type: str = Form(...)

):



    front_bytes = await front_image.read()
    back_bytes = await back_image.read()

    front_base64 = base64.b64encode(front_bytes).decode("utf-8")
    back_base64 = base64.b64encode(back_bytes).decode("utf-8")

    response = client.responses.create(
        model="gpt-4o-mini",
        temperature=0,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": """ 
                        Analyze both alcohol label images. 
                        The first image is the front label. 
                        The second image is the back label. 
                        Extract: 
                        - brand_name
                        - class_type
                        - alcohol_content
                        - net_contents
                        - government_warning 
                        
                        For brand_name, extract ONLY the brand name.

                        Example: 
                        Brand Name = Captain John's
                        NOT Captain John's Spiced Rum

                        Do not combine brand names with product names,
                        fanciful names, class/type designations,
                        or flavorful descriptions.

                        For class_type, extract the official Class, Type, Other Designation exactly as it appears on the label.

                        Examples:

                        Brand Name: Captain John's
                        Distinctive/Fanciful Name: Spiced Rum
                        Class/Type/Other Designation: Rum with Natural Flavors Added

                        For alcohol_content, extract ONLY the alcohol by volume percentage.

                        Examples:
                        20%
                        13.5%
                        5%

                        Do not include:
                        Alcohol By Volume
                        Proof
                        ABV

                        Return valid JSON only.
                        Do not use markdown.
                        Do not wrap the response in triple backticks.
                        """
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{front_image.content_type};base64,{front_base64}"
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{back_image.content_type};base64,{back_base64}"
                    }
                ]
            }
        ]
    )

    raw_output = response.output_text

    print("RAW OPEN AI OUTPUT:", repr(raw_output))

    if not raw_output:
        return {
            "error": "OpenAI returned empty output",
            "raw_output": raw_output
        }
    try:
        extracted = json.loads(raw_output)
    except json.JSONDecodeError:
        return {
            "error": "OpenAI did not return valid JSON",
            "raw_output": raw_output
        }

    validation = {
        "brand_name": check_match(expected_brand_name, extracted.get("brand_name")),
        "class_type": check_match(expected_class_type, extracted.get("class_type")),
        "alcohol_content": check_match(expected_alcohol_content, extracted.get("alcohol_content")),
        "net_contents": check_match(expected_net_contents, extracted.get("net_contents")),
        "government_warning": "PRESENT" if extracted.get("government_warning") else "MISSING"
    }
    
    return {
    "extracted": extracted,
    "validation": validation
    }