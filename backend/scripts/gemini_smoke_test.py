from app.clients import get_gemini_client


def main():
    response = get_gemini_client().models.generate_content(
        model="gemini-2.5-flash",
        contents="Say hello",
    )
    print(response.text)


if __name__ == "__main__":
    main()
