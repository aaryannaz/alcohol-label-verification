from app.clients import GEMINI_MODEL, get_gemini_client


def main():
    response = get_gemini_client().models.generate_content(
        model=GEMINI_MODEL,
        contents="Say hello",
    )
    print(f"Model: {GEMINI_MODEL}")
    print(response.text)


if __name__ == "__main__":
    main()
