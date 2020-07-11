client_id = "c8b0bf91f2f54f34ba63256f3d009ee8"
client_secret = "7d7e6ba01b4b4734961635b074849190"
spotify_token = "BQCJmzvlu49TLRVqV0RhiXvIyec17Nl5dbHEhJ42L25zl2YWUvuTRPpCeRs_Lf_cDVs60x4aKTryxnpMIMWKDx2MBV4kLhe4niV3aS1h-1DRKh3I8eg_efx1iSsvgrWlTNCFPT8jnJ9ua2E2LCjRomBb4j3gh_ajJaHjVQ8cd0iRrwMpF8P3b-Nm5Bt9pqxRojeBtOzXjA"
user_id = "yagnab"

redirect_url = "https%3A%2F%2Fwww.google.com%2F"
scope = ["playlist-modify-public", "playlist-modify-private"]
get_uri = "https://accounts.spotify.com/authorize?client_id={0}&response_type=code&redirect_uri={1}&scope={2}".format(
    client_id,
    redirect_url,
    "%20".join(scope),
)

post_uri = "https://accounts.spotify.com/api/token"

base64IdSecret = "YzhiMGJmOTFmMmY1NGYzNGJhNjMyNTZmM2QwMDllZTg6N2Q3ZTZiYTAxYjRiNDczNDk2MTYzNWIwNzQ4NDkxOTA="

code = "AQDwL2kKNcs8cdA7LXpGiM8hfnrJ79GRlpHmty7tgpUKD-65aJY4CdPWDSsiTaXn1NGGnWHie4oCpWuXKCow6mY1IuAQdKMSfGOFZd_OmYhR9uGkQFaNLHTkjvFiKBJKgrt2g8RoGQQam3WyEcDQ9cTTfE-pTllyYflSQgvS_woWS6ABZUXv6oU-aKPbuke2_kGiKIBXY-8qIXs1hYJj36u-NXfnowo91QzN4w"

curl_cmd = "curl -H 'Authorization: Basic {0}' " \
    "-d grant_type=authorization_code " \
    "-d code={2} " \
    "-d redirect_uri={1} " \
    "https://accounts.spotify.com/api/token".format(base64IdSecret, redirect_url, code)

# print(curl_cmd)

# {
#     "access_token": "BQCJmzvlu49TLRVqV0RhiXvIyec17Nl5dbHEhJ42L25zl2YWUvuTRPpCeRs_Lf_cDVs60x4aKTryxnpMIMWKDx2MBV4kLhe4niV3aS1h-1DRKh3I8eg_efx1iSsvgrWlTNCFPT8jnJ9ua2E2LCjRomBb4j3gh_ajJaHjVQ8cd0iRrwMpF8P3b-Nm5Bt9pqxRojeBtOzXjA",
#     "token_type":"Bearer",
#     "expires_in":3600,
#     "refresh_token":"AQASx8bx4tvwjhpkHppo2NE_CxR_AYpgDbcc6EFGHLOvg8in__H2jQRlSsH8X8Y3h-3buL1OJus9z5QzARntgkhYkFVVWGBeu-ncGW3A2prFPdI8EZM_94wRh6Zsz_k5lOc",
#     "scope":"playlist-modify-private playlist-modify-public"
# }