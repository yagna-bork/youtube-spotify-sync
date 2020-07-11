import requests
import json
import os

from secrets import spotify_token, user_id

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

import youtube_dl

class CreatePlaylist:
    def __init__(self):
        self.user_id = user_id
        self.token = spotify_token
        self.youtube_client = self.get_youtube_api()
        self.liked_songs_info = {}

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

        # TODO client_secret set to installed might be an issue
        return youtube_client

    # get all liked youtube videos & store information song information about each video
    # TODO is every video even non music video added?
    def get_liked_videos(self):
        request = self.youtube_client.videos().list(
            part='snippet,contentDetails',
            myRating='like'
        )
        response = request.execute()

        for item in response['items']:
            video_title = item["snippet"]["title"]
            youtube_url = "https://www.youtube.com/watch?v={}".format(item['id'])

            # use youtube to parse song information
            print(youtube_url)
            video = youtube_dl.YoutubeDL({}).extract_info(youtube_url, False)

            song_name = video['track']
            artist = video['artist']

            # save information
            self.liked_songs_info[video_title] = {
                "youtube_url": youtube_url,
                "song_name": song_name,
                "artist": artist,

                # spotify resource uri for easy access
                "spotify_uri": self.get_song_spotify_uri(song_name, artist)
            }

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

    def add_songs_to_playlist(self): #TODO timestamp so only new entries added
        self.get_liked_videos()
        song_uris = [info['spotify_uri'] for _, info in self.liked_songs_info.items()]
        new_playlist_id = self.create_playlist()

        request_data = json.dumps(song_uris)

        query = "https://api.spotify.com/v1/playlists/{}/tracks".format(new_playlist_id)

        # position left empty -> songs appended
        request_body = json.dumps({
            "uris": request_data
        })

        response = requests.post(
            query,
            data=request_body,
            headers={
                "Authorization": "Bearer {}".format(self.token),
                "Content-Type": "application/json"
            }
        )

        return response.json()

if __name__ == '__main__':
    cp = CreatePlaylist()
    cp.add_songs_to_playlist()