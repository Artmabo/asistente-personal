import logging
import os
import stat
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# gmail.modify covers everything this app does (read, label, archive, trash) without
# the permanent-delete/settings/send access that the full https://mail.google.com/
# scope would grant — least privilege in case token.json is ever leaked or misused.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def get_service(
    creds_path: str = "config/credentials.json",
    token_path: str = "token.json",
):
    """Builds and returns an authenticated Gmail API service."""
    creds = None

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except (ValueError, OSError):
            # token.json exists but is corrupted/truncated (e.g. process killed
            # mid-write) — fall through to a full re-auth instead of crashing.
            logging.getLogger("gmail_processor.auth").warning(
                f"'{token_path}' is corrupted or unreadable — re-authenticating."
            )
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # Refresh token revoked or network failure — force full re-auth
                creds = None
        if not creds or not creds.valid:
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
