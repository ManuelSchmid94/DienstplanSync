"""
Google OAuth2 flow for installed desktop applications.
Token is stored in APP_DATA_DIR/token.json.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_credentials(
    credentials_file: Path,
    token_file: Path,
) -> Credentials:
    """
    Return valid Google OAuth2 credentials.
    Refreshes automatically if a saved token exists.
    Launches browser-based OAuth flow if no valid token is found.
    """
    creds: Optional[Credentials] = None

    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except Exception as e:
            logger.warning("Konnte Token nicht laden: %s", e)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds, token_file)
            logger.info("Access Token erneuert.")
            return creds
        except Exception as e:
            logger.warning("Token-Refresh fehlgeschlagen: %s – starte neu.", e)

    # Full OAuth flow
    if not credentials_file.exists():
        raise FileNotFoundError(
            f"credentials.json nicht gefunden: {credentials_file}\n"
            "Bitte Google Cloud Console aufrufen und OAuth2-Client-ID erstellen."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    _save_token(creds, token_file)
    logger.info("Google-Authentifizierung erfolgreich.")
    return creds


def revoke_token(token_file: Path) -> None:
    """Delete saved token to force re-authentication next time."""
    if token_file.exists():
        token_file.unlink()
        logger.info("Token gelöscht.")


def _save_token(creds: Credentials, token_file: Path) -> None:
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json())
    logger.debug("Token gespeichert: %s", token_file)
