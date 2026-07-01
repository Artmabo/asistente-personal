from __future__ import print_function
import os
import os.path
import stat
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service(creds_path="config/credentials.json", token_path="token.json"):

    creds = None

    # Si ya existe token
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except (ValueError, OSError):
            # token.json corrupto o malformado — forzar re-autenticación completa
            creds = None

    # Si no hay credenciales válidas
    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                creds_path,
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        # Guardar token (tanto si fue refrescado como si es nuevo) con permisos 0600
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w") as token:
            token.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds)

    return service


def main():

    service = get_gmail_service()

    results = service.users().labels().list(userId="me").execute()

    labels = results.get("labels", [])

    print("\nEtiquetas en tu Gmail:\n")

    for label in labels:
        print(label["name"])


if __name__ == "__main__":
    main()