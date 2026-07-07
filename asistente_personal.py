"""Delegates to gmail_processor.auth so every entry point shares one
OAuth flow, one scope, and one securely-permissioned token.json."""
from gmail_processor.auth import get_service


def get_gmail_service(creds_path="config/credentials.json", token_path="token.json"):
    return get_service(creds_path=creds_path, token_path=token_path)


def main():

    service = get_gmail_service()

    results = service.users().labels().list(userId="me").execute()

    labels = results.get("labels", [])

    print("\nEtiquetas en tu Gmail:\n")

    for label in labels:
        print(label["name"])


if __name__ == "__main__":
    main()