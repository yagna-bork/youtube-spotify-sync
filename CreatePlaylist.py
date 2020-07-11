import requests
import json
import os

from secrets import spotify_token, user_id

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

class CreatePlaylist:
    def __init__(self):
        self.user_id = user_id
        self.token = spotify_token

    def get_youtube_api(self):
        """ Log Into Youtube, Copied from Youtube Data API """
        # Disable OAuthlib's HTTPS verification when running locally.
        # *DO NOT* leave this option enabled in production.
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

        api_service_name = "youtube"
        api_version = "v3"
        client_secrets_file = "client_secret.json"

        # Get credentials and create an API client
        scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            client_secrets_file, scopes)
        credentials = flow.run_console()

        # from the Youtube DATA API
        youtube_client = googleapiclient.discovery.build(
            api_service_name, api_version, credentials=credentials)

        return youtube_client

    def get_liked_vids(self):
        pass

    # Create corresponding playlist on Spotify
    def create_playlist(self):
        request_body = json.dumps({
            "name": "Youtube Liked Videos",
            "description": "Songs which are on your liked videos playlist from YouTube",
            "public": False
        })
        endpoint = "https://api.spotify.com/v1/users/{}/playlists".format(self.user_id)

        response = requests.post(
            endpoint,
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(self.token)
            }
        )
        response_json = response.json()

        return response_json["id"]

    def get_song_spotify_uri(self, song_name, artist):
        q = "{0}+{1}".format(song_name, artist)
        spotify_type = "track"
        market = "UK"
        limit = 1 #TODO: Might cause issue

        endpoint = "https://api.spotify.com/v1/search?q={0}&type={1}&market={2}&limit={3}".format(
            q, spotify_type, market, limit)

        response = requests.get(
            endpoint,
            header={
                "Authorization": "Bearer {}".format(self.token)
            }
        )
        response_json = response.json()

        # uri of first song from query results
        return response_json['tracks']['items'][0]['uri']


    def add_song_to_playlist(self):
        pass

