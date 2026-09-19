"""
Legacy entry point kept for backward compatibility with ejemplos*.py.
Delegates authentication to gmail_processor.auth (which handles token
refresh failures and restricts token.json permissions to the owner).
"""
from __future__ import print_function

from gmail_processor.auth import get_service


def get_gmail_service(creds_path="config/credentials.json", token_path="token.json"):
    """Builds and returns an authenticated Gmail API service."""
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
