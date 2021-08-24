import typing as t
import google_auth_oauthlib.flow
import google.oauth2.credentials
import google.auth.transport.requests
import google.auth.exceptions
import googleapiclient.discovery
import googleapiclient.errors
import json
from utils import CacheKeyringHandler


_google_keyring_handler = CacheKeyringHandler("yt2spotifysync", "google_cached_info")


def _do_google_auth_flow(scopes: t.List[str]) -> google.oauth2.credentials.Credentials:
    secrets_file = "client_secret.json"
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(secrets_file, scopes)
    return flow.run_console()


def _get_google_apis_credentials(scopes: t.List[str]) -> google.oauth2.credentials.Credentials:
    user_info = None
    if user_info_json := _google_keyring_handler.get_cached_token():
        user_info = json.loads(user_info_json)
    if user_info:
        credentials = google.oauth2.credentials.Credentials.from_authorized_user_info(user_info)
        if credentials.valid:
            return credentials
        else:
            try:
                request = google.auth.transport.requests.Request()
                credentials.refresh(request)
            except google.auth.exceptions.RefreshError:
                print("Something went wrong with refreshing your google access token. Let's make a new one!")
            else:
                _google_keyring_handler.save_token_to_cache(credentials.to_json())
                return credentials

    credentials = _do_google_auth_flow(scopes)
    _google_keyring_handler.save_token_to_cache(credentials.to_json())
    return credentials


def get_youtube_api():
    scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
    credentials = _get_google_apis_credentials(scopes)
    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)
