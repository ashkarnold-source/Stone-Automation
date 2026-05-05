"""
Gmail OAuth2 integration.

Setup steps:
1. Go to console.cloud.google.com → Create project → Enable Gmail API
2. Create OAuth2 credentials (Web Application type)
3. Add http://localhost:8000/auth/gmail/callback as an authorized redirect URI
4. Copy Client ID and Secret to your .env file
"""
import os
import json
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

TOKEN_FILE = "data/gmail_token.json"


def get_auth_url() -> str:
    flow = _build_flow()
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return auth_url


def handle_callback(code: str) -> bool:
    flow = _build_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    os.makedirs("data", exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    return True


def is_authenticated() -> bool:
    return os.path.exists(TOKEN_FILE)


def send_email(to_email: str, subject: str, body: str, html: bool = False) -> dict:
    service = _get_service()
    if not service:
        return {"success": False, "error": "Gmail not authenticated"}

    from_email = os.getenv("FROM_EMAIL", "")
    from_name = os.getenv("FROM_NAME", "Ashley Stennis")

    message = MIMEMultipart("alternative")
    message["to"] = to_email
    message["from"] = f"{from_name} <{from_email}>"
    message["subject"] = subject

    if html:
        message.attach(MIMEText(body, "html"))
    else:
        message.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"success": True, "message_id": result.get("id")}


def get_recent_replies(max_results: int = 20) -> list:
    service = _get_service()
    if not service:
        return []

    results = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=max_results,
        q="is:unread"
    ).execute()

    messages = results.get("messages", [])
    replies = []
    for msg in messages:
        detail = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        replies.append({
            "id": msg["id"],
            "from": headers.get("From"),
            "subject": headers.get("Subject"),
            "date": headers.get("Date"),
        })
    return replies


def _get_service():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE) as f:
        creds_data = json.load(f)
    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
    return build("gmail", "v1", credentials=creds)


def _build_flow() -> Flow:
    client_config = {
        "web": {
            "client_id": os.getenv("GMAIL_CLIENT_ID"),
            "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
            "redirect_uris": [os.getenv("GMAIL_REDIRECT_URI", "http://localhost:8000/auth/gmail/callback")],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(client_config, scopes=SCOPES,
                                   redirect_uri=os.getenv("GMAIL_REDIRECT_URI",
                                                          "http://localhost:8000/auth/gmail/callback"))
