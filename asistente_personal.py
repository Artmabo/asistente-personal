from __future__ import print_function
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service(creds_path="config/credentials.json", token_path="token.json"):

    creds = None

    # Si ya existe token
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        print("\nTOKEN CARGADO:")
        print(creds.scopes)

    # Si no hay credenciales válidas
    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                creds_path,
                SCOPES
            )

            creds = flow.run_local_server(port=0)

            print("\nSCOPES DEL TOKEN:")
            print(creds.scopes)

        # Guardar token
        with open(token_path, "w") as token:
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