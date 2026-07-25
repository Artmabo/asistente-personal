from __future__ import print_function


def get_gmail_service(creds_path="config/credentials.json", token_path="token.json"):
    """Builds an authenticated Gmail service.

    Delegates to gmail_processor.auth.get_service, which handles token
    refresh failures (re-auths instead of raising) and writes token.json
    with owner-only permissions (0600) instead of the default umask.
    """
    from gmail_processor.auth import get_service
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