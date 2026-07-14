"""
Legacy entry point kept for backwards compatibility with ejemplos*.py.
The OAuth flow itself lives in gmail_processor.auth (handles refresh-token
revocation and writes token.json with owner-only permissions).
"""
from gmail_processor.auth import get_service as get_gmail_service


def main():

    service = get_gmail_service()

    results = service.users().labels().list(userId="me").execute()

    labels = results.get("labels", [])

    print("\nEtiquetas en tu Gmail:\n")

    for label in labels:
        print(label["name"])


if __name__ == "__main__":
    main()