__all__ = ["get_youtube_api", "get_spotify_api"]


import typing as t
import google_auth_oauthlib.flow
import google.oauth2.credentials
import google.auth.transport.requests
import google.auth.exceptions
import googleapiclient.discovery
import googleapiclient.errors
import keyring
import spotipy
from spotipy.oauth2 import SpotifyPKCE
from spotipy.cache_handler import CacheHandler
import json
from contextlib import contextmanager


class CacheKeyringHandler(CacheHandler):
    """
    Handles reading and writing cached Spotify authorization tokens
    as json object in the system keyring.
    """

    def __init__(self, keyring_service_id, key):
        """
        Parameters:
             * keyring_service_id: The service id that will be associated with your apps keyring storage
        """
        self.keyring_service_id = keyring_service_id
        self.key = key

    def get_cached_token(self):
        token_info = None

        try:
            result = keyring.get_password(self.keyring_service_id, self.key)
            token_info = json.loads(result) if result else None
        except keyring.errors.InitError:
            print('Couldn\'t initalise the %s keyring service while trying to read', self.keyring_service_id)

        return token_info

    def save_token_to_cache(self, token_info):
        try:
            keyring.set_password(self.keyring_service_id, self.key, json.dumps(token_info))
        except keyring.errors.PasswordSetError:
            print('Couldn\'t write token to the %s keyring service', self.keyring_service_id)
        except keyring.errors.InitError:
            print('Couldn\'t initalise the %s keyring service while trying to write', self.keyring_service_id)


_spotify_keyring_handler = CacheKeyringHandler("yt2spotifysync", "spotify_cached_info")
_google_keyring_handler = CacheKeyringHandler("yt2spotifysync", "google_cached_info")


def _do_google_auth_flow(scopes: t.List[str]) -> google.oauth2.credentials.Credentials:
    secrets_file = "client_secret.json"
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(secrets_file, scopes)
    return flow.run_console()


def _build_credentials(credentials_json: str) -> google.oauth2.credentials.Credentials:
    credentials_dict = json.loads(credentials_json)
    return google.oauth2.credentials.Credentials.from_authorized_user_info(credentials_dict)


def _get_google_apis_credentials(scopes: t.List[str]) -> google.oauth2.credentials.Credentials:
    credentials_json = _google_keyring_handler.get_cached_token()
    if credentials_json:
        credentials = _build_credentials(credentials_json)
        if credentials.valid:
            return credentials
        else:
            try:
                request = google.auth.transport.requests.Request()
                credentials.refresh(request)
            except google.auth.exceptions.RefreshError:
                print("Something went wrong with refreshing your google access token. Let's make a new one.")
            else:
                _google_keyring_handler.save_token_to_cache(credentials.to_json())
                return credentials

    credentials = _do_google_auth_flow(scopes)
    credentials_json = credentials.to_json()
    _google_keyring_handler.save_token_to_cache(credentials_json)
    return credentials


def get_youtube_api():
    scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
    credentials = _get_google_apis_credentials(scopes)
    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)


@contextmanager
def get_spotify_api():
    with open("spotify_secrets.json", "r") as file:
        spotify_secrets = json.load(file)
    sp = spotipy.Spotify(
        auth_manager=SpotifyPKCE(
            client_id=spotify_secrets["client_id"],
            redirect_uri=spotify_secrets["redirect_uri"],
            scope=" ".join(spotify_secrets["scope"]),
            cache_handler=_spotify_keyring_handler,
        )
    )
    try:
        yield sp
    finally:
        sp.__del__()
