"""
Punto de entrada heredado — delega en gmail_processor.auth para evitar
duplicar la lógica de autenticación (manejo de tokens revocados, permisos
del archivo token.json, etc.).
"""
from __future__ import print_function


def get_gmail_service(creds_path="config/credentials.json", token_path="token.json"):
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