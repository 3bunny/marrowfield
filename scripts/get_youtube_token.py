#!/usr/bin/env python3
"""
One-time helper. Run this ONCE on your own computer to mint a YouTube refresh
token, then paste the printed values into your GitHub repository secrets.

  pip install google-auth-oauthlib
  python scripts/get_youtube_token.py client_secret.json

A browser window opens. Sign in with the Google account that owns the channel,
and when the account picker appears, choose the "The Same Room" brand channel —
not your personal channel. Getting this wrong is the single most common way this
setup goes sideways, and the symptom is videos quietly landing on the wrong
channel.
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts/get_youtube_token.py path/to/client_secret.json")

    secret_file = Path(sys.argv[1])
    if not secret_file.exists():
        sys.exit(f"Not found: {secret_file}")

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    if not creds.refresh_token:
        sys.exit(
            "No refresh token came back. Revoke the app's access at "
            "https://myaccount.google.com/permissions and run this again."
        )

    data = json.loads(secret_file.read_text(encoding="utf-8"))
    installed = data.get("installed") or data.get("web") or {}

    print("\n" + "=" * 68)
    print("Add these three as GitHub repository secrets:")
    print("=" * 68)
    print(f"\nYT_CLIENT_ID\n{installed.get('client_id', '')}")
    print(f"\nYT_CLIENT_SECRET\n{installed.get('client_secret', '')}")
    print(f"\nYT_REFRESH_TOKEN\n{creds.refresh_token}")
    print("\n" + "=" * 68)
    print("Do not commit these to the repository. Secrets only.")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    main()
