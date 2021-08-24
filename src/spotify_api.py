import json
import tekore as tk
from utils import CacheKeyringHandler
import webbrowser
import typing as t
import time
from contextlib import asynccontextmanager


_spotify_keyring_handler = CacheKeyringHandler("yt2spotifysync", "spotify_secret_token_info")


class SpotifyAPI(tk.Spotify):
    @classmethod
    async def get_instance(cls, *args: t.Any, **kwargs: t.Any) -> "SpotifyAPI":
        """Return an instance of SpotifyAPI with user_id initialized for convenience."""
        inst = cls(*args, **kwargs)
        inst._user_id = (await inst.current_user()).id
        return inst

    async def get_song_uri(self, artist: str, title: str) -> t.Optional[str]:
        q = artist.replace(" ", "+").strip() + "+" + title.replace(" ", "+").strip()
        page, = await self.search(q, limit=1)
        return page.items[0].uri if page.total > 0 else None

    async def playlist_create(self, name: str, public: bool) -> tk.model.FullPlaylist:
        description = f"Spotify synced version of the {name} playlist from your YouTube"
        return await super().playlist_create(self._user_id, name, public, description)


def save_token(token: tk.Token) -> None:
    token_info = {
        "access_token": token.access_token,
        "expires_at": token.expires_at,
        "refresh_token": token.refresh_token,
        "token_type": token.token_type,
    }
    _spotify_keyring_handler.save_token_to_cache(json.dumps(token_info))


def load_token() -> t.Optional[tk.Token]:
    if not (token_info_json := _spotify_keyring_handler.get_cached_token()):
        return None
    token_info = json.loads(token_info_json)
    # unfortunately expires_in isn't calculated in the token constructor so we need to do it # TODO submit PR
    token_info["expires_in"] = token_info["expires_at"] - int(time.time())
    return tk.Token(token_info, uses_pkce=True)


def prompt_user_for_redirected_url(auth_url: str) -> str:
    print("Taking you to spotify login...")
    webbrowser.open(auth_url)
    return input("Paste the redirected URL below: ").strip()


def get_access_token() -> tk.Token:
    with open("spotify_config.json", "r") as file:
        conf = json.load(file)
    client_id, redirect_uri, scopes = conf["client_id"], conf["redirect_uri"], conf["scopes"]

    cred = tk.Credentials(client_id, redirect_uri=redirect_uri, sender=tk.RetryingSender(retries=3))
    if token := load_token():
        if not token.is_expiring:
            return token
        else:
            try:
                token = cred.refresh_pkce_token(token.refresh_token)
            except tk.HTTPError as e:
                print("Something went wrong while refreshing your spotify token. Lets make you a new one!")
            else:
                save_token(token)
                return token

    auth = tk.UserAuth(cred, scopes, pkce=True)
    redirected = prompt_user_for_redirected_url(auth.url)
    token = auth.request_token(url=redirected)
    save_token(token)
    return token


@asynccontextmanager
async def get_spotify_api() -> SpotifyAPI:
    """Return an async API for spotify that can retry a call upto 3 times."""
    token = get_access_token()
    sender = tk.RetryingSender(retries=3, sender=tk.AsyncSender())
    spotify_api = await SpotifyAPI.get_instance(token, sender=sender, max_limits_on=True, chunked_on=True)
    try:
        yield spotify_api
    finally:
        await spotify_api.close()
