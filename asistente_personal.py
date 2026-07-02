"""
Punto de entrada legacy — delega en gmail_processor.auth para reutilizar
el flujo de autenticación reforzado (permisos restrictivos en token.json,
recuperación automática si el refresh token fue revocado).
"""
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