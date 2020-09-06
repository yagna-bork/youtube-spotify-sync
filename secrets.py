client_id = "c8b0bf91f2f54f34ba63256f3d009ee8"
client_secret = "7d7e6ba01b4b4734961635b074849190"
user_id = "yagnab"

redirect_url = "https%3A%2F%2Fwww.google.com%2F"
scope = ["playlist-modify-public", "playlist-modify-private"]
get_uri = "https://accounts.spotify.com/authorize?client_id={0}&response_type=code&redirect_uri={1}&scope={2}".format(
    client_id,
    redirect_url,
    "%20".join(scope),
)

base64_id_secret = "YzhiMGJmOTFmMmY1NGYzNGJhNjMyNTZmM2QwMDllZTg6N2Q3ZTZiYTAxYjRiNDczNDk2MTYzNWIwNzQ4NDkxOTA="