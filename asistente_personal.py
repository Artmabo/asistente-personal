"""
Punto de entrada simple: autentica con Gmail y lista las etiquetas.

La autenticación real vive en gmail_processor/auth.py (maneja permisos
seguros del token y reintentos de refresh); este módulo sólo delega ahí
para no mantener un segundo flujo OAuth con su propio SCOPES y sus propios
bugs.
"""
from gmail_processor.auth import get_service


def get_gmail_service(creds_path="config/credentials.json", token_path="token.json"):
    """Alias retro-compatible de gmail_processor.auth.get_service."""
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
