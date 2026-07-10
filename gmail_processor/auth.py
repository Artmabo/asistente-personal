import os
import stat
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://mail.google.com/"]


def get_service(
    creds_path: str = "config/credentials.json",
    token_path: str = "token.json",
    interactive: bool = True,
):
    """Builds and returns an authenticated Gmail API service.

    interactive=False raises instead of launching the browser-based OAuth flow.
    Use this from background contexts (e.g. the APScheduler thread) where there
    is no browser/console to complete the flow — run_local_server() would
    otherwise block that thread forever waiting on a login that never happens.
    """
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # Refresh token revoked or network failure — force full re-auth
                creds = None
        if not creds or not creds.valid:
            if not interactive:
                raise RuntimeError(
                    "Se requiere reautenticación interactiva con Gmail (el token "
                    "expiró o fue revocado) y no hay una sesión interactiva disponible."
                )
            if not os.path.exists(creds_path):
                raise FileNotFoundError(
                    f"No se encontró el archivo de credenciales en '{creds_path}'. "
                    "Descarga el archivo OAuth 2.0 desde Google Cloud Console y "
                    "guárdalo como config/credentials.json. "
                    "Consulta config/README.md para instrucciones detalladas."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)
