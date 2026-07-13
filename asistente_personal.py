from __future__ import print_function

from gmail_processor.auth import get_service


def get_gmail_service(creds_path="config/credentials.json", token_path="token.json"):
    """Builds an authenticated Gmail service. Delegates to gmail_processor.auth.

    This used to be a standalone re-implementation of the OAuth flow; it now
    delegates so there is a single, correctly-hardened auth path (handles
    expired/revoked refresh tokens and writes token.json with 0600 perms).
    """
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