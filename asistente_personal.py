from __future__ import print_function

from gmail_processor.auth import get_service


def get_gmail_service(creds_path="config/credentials.json", token_path="token.json"):
    """Thin wrapper kept for backwards compatibility — delegates to the
    single, hardened auth implementation in gmail_processor.auth so token
    refresh errors, file permissions, and scopes stay in one place."""
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