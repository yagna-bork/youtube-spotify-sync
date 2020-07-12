import requests
import json
import os

from secrets import user_id, get_uri, redirect_url
from storage_manager import StorageManager
from input_manger import get_inputs

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

from youtube_title_parse import get_artist_title

input_field_to_col = {
    "playlist_id": 0,
    "download": 1
}

class CreatePlaylist:
    def __init__(self):
        self.user_id = user_id
        # self.token = self.get_spotify_token()
        self.token = "BQC_cwE6AUi_gkX5a5ez0rQSZFdrH_W4Hyx75L64SDI4qiqf1UuGYQ0TgDLSclLz9Uy2itv2LoMzBs4CkVtBXF3_4mAnY5VGpK6z0siM6goQx4cRbFHwrct7gJZzbuPwknBc13pJBMpwcR-KrL1yJ-LC6yaz6qXP6ayZBKcyjmD2TMqBrcKmlVSDV0d5p9MlQeA3kcWp_A"
        self.youtube_client = self.get_youtube_api()
        self.liked_songs_info = {}
        self.storage = StorageManager()

    def get_spotify_token(self):
        print("Access this uri for spotify authorization:\n{}".format(get_uri))

        post_uri = "https://accounts.spotify.com/api/token"
        base64_id_secret = "YzhiMGJmOTFmMmY1NGYzNGJhNjMyNTZmM2QwMDllZTg6N2Q3ZTZiYTAxYjRiNDczNDk2MTYzNWIwNzQ4NDkxOTA="

        code = input("Enter the code you got back: ")

        curl_cmd = "curl -H 'Authorization: Basic {0}' " \
                   "-d grant_type=authorization_code " \
                   "-d code={2} " \
                   "-d redirect_uri={1} " \
                   "https://accounts.spotify.com/api/token".format(base64_id_secret, redirect_url, code)

        print("Use this curl command:\n{}".format(curl_cmd))
        spotify_token = input("Enter the spotify token: ")

        return spotify_token

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
    def extract_and_save_playlist_songs(self, playlist_id):
        request = self.youtube_client.playlistItems().list(
            part="snippet,contentDetails",
            maxResults=50, # TODO make this as long as the playlist
            # id of my personal liked videos playlist
            # TODO identify this id automatically
            playlistId=playlist_id
        )

        while True:
            response = request.execute()

            for item in response['items']:
                video_title = item["snippet"]["title"]
                youtube_url = "https://www.youtube.com/watch?v={}".format(item['contentDetails']['videoId'])

                # TODO Use new version of youtube-dl that implements this fix
                try:
                    artist, song_name = get_artist_title(video_title)

                    # print("Title: {0}\nSong name: {1}\nArtist: {2}".format(video_title, song_name, artist))

                    spotify_uri = self.get_song_spotify_uri(song_name, artist)
                    if spotify_uri != -1:
                        self.liked_songs_info[video_title] = {
                            "youtube_url": youtube_url,
                            "song_name": song_name,
                            "artist": artist,

                            # spotify resource uri for easy access
                            "spotify_uri": self.get_song_spotify_uri(song_name, artist)
                        }
                except:
                    print("Could not find song name and artist from {0} at {1}".format(video_title, youtube_url))

            if 'nextPageToken' in response:
                request = self.youtube_client.playlistItems().list(
                    part="snippet,contentDetails",
                    maxResults=50, # TODO make this as long as the playlist
                    # id of my personal liked videos playlist
                    # TODO identify this id automatically
                    playlistId="LLEA6rXRPPbQur1xyOgurtQg",
                    pageToken=response['nextPageToken']
                )
            else:
                break

    def get_playlist_name(self, playlist_id):
        request = self.youtube_client.playlists().list(
            part="snippet",
            id=playlist_id
        )

        response = request.execute()
        return response['items'][0]['snippet']['title']

    # Create corresponding playlist on Spotify
    def create_playlist(self, name, public=True):
        request_body = json.dumps({
            "name": name,
            "description": "Spotify synced version of the {} playlist from your YouTube".format(name),
            "public": public
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

        if 'error' in response_json:
            print("Response after sending request to create playlist: \n{}".format(response_json))
            return -1 # TODO replace all -1 with proper error handling
        else:
            return response_json["id"]

    def get_song_spotify_uri(self, song_name, artist):
        q = "{0}+{1}".format(song_name, artist)
        spotify_type = "track"
        market = "GB"
        limit = 1 #TODO: Might cause issue

        endpoint = "https://api.spotify.com/v1/search?q={0}&type={1}&market={2}&limit={3}".format(
            q, spotify_type, market, limit)

        response = requests.get(
            endpoint,
            headers={
                "Authorization": "Bearer {}".format(self.token)
            }
        )

        response_json = response.json()
        returned_songs = response_json['tracks']['items']

        # TODO suggest alternative for failed songs command line feature
        if len(returned_songs) > 0:
            # uri of first song from query results
            return returned_songs[0]['uri']
        else:
            return -1

    def add_songs_to_playlist(self): #TODO timestamp so only new entries added
        # TODO write class to handle input file reading
        playlist_id = ""
        with open('input.csv') as file:
            reader = csv.reader(file)

            for idx, row in enumerate(reader):
                playlist_id = row[0]
                break

        self.extract_and_save_playlist_songs(playlist_id)
        song_uris = [info['spotify_uri'] for _, info in self.liked_songs_info.items()]
        new_playlist_id = self.create_playlist()

        while len(song_uris) > 0:
            # max 100 songs per request
            num_songs_current_req = min(100, len(song_uris))
            request_data = json.dumps(song_uris[:num_songs_current_req])
            song_uris = song_uris[num_songs_current_req:]

            query = "https://api.spotify.com/v1/playlists/{}/tracks".format(new_playlist_id)

            response = requests.post(
                query,
                data=request_data,
                headers={
                    "Authorization": "Bearer {}".format(self.token),
                    "Content-Type": "application/json"
                }
            )

            print(response.json())

        # write as changes may have been made
        self.storage.write_storage()

    def sync_playlists(self):
        for yt_playlist_id, download in get_inputs().items():
            if self.storage.has_playlist_been_synced(yt_playlist_id):
                print("{} has been synced before".format(yt_playlist_id))
            else:
                print("{} has not been synced before".format(yt_playlist_id))

                yt_playlist_name = self.get_playlist_name(yt_playlist_id)
                spotify_playlist_id = self.create_playlist(yt_playlist_name)

                # create spotify pl with correct name, description and return correct id
                print(yt_playlist_name)
                print(spotify_playlist_id)

            break


if __name__ == '__main__':
    cp = CreatePlaylist()
    # cp.add_songs_to_playlist()

    cp.sync_playlists()

