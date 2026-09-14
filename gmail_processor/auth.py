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

    interactive=False raises instead of launching a browser-based OAuth flow —
    use it for unattended callers (e.g. the background cleanup scheduler) so a
    revoked/expired token fails fast rather than hanging a worker thread
    waiting on a local-server redirect that will never arrive.
    """
    creds = None

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except (ValueError, OSError):
            # Corrupt/truncated token file — fall through to re-auth below
            creds = None

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
                    "No hay credenciales válidas y interactive=False: no se puede "
                    "iniciar el flujo de OAuth en un proceso sin usuario presente."
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
        _write_token_atomic(token_path, creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _write_token_atomic(token_path: str, content: str) -> None:
    """Writes the token file via temp-file + rename so a crash mid-write can
    never leave a truncated token.json behind."""
    tmp_path = f"{token_path}.tmp"
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, token_path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
