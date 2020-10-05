import requests
import json
import os
from datetime import datetime, timezone
import youtube_dl

from secrets import user_id, get_uri, redirect_url, base64_id_secret
from storage_manager import StorageManager
from input_manger import get_inputs
from datetime_manager import gmt_to_local_timezone, parse_youtube_datetime

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
        self.token = self.get_spotify_token()
        # self.token = "BQDrinai7m8XjfaCVdQR2cEF9DvraTu93UVSL0IUsgAlPOL3Z9EvQHqMa3aXJ-Md4utDPHOl984dqTWMDCBtXE6r3Db6pUfGLrz-qDHa9_BuNn81OBT_hFFDOOzu0k8xjVI9kRZACJawjlDUaZ-oymVUVZJabblgd6W4bC_IJPh6JYVpCZgrMqvyYrmuScdi0UErVRZ-Gg"
        self.youtube_client = self.get_youtube_api()
        self.liked_songs_info = {}
        self.storage = StorageManager()
        self.local_files_path = "~/Music/spotify"

    @staticmethod
    def get_spotify_token():
        print("Access this uri for spotify authorization:\n{}".format(get_uri))

        post_uri = "https://accounts.spotify.com/api/token"

        code = input("Enter the code you got back: ")

        curl_cmd = "curl -H 'Authorization: Basic {0}' " \
                   "-d grant_type=authorization_code " \
                   "-d code={2} " \
                   "-d redirect_uri={1} " \
                   "https://accounts.spotify.com/api/token".format(base64_id_secret, redirect_url, code)

        print("Use this curl command:\n{}".format(curl_cmd))
        spotify_token = input("Enter the spotify token: ")

        return spotify_token

    @staticmethod
    def get_youtube_api():
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

    # returns song name, artist and spotify id
    # TODO Use new version of youtube-dl that implements this fix
    def get_spotify_id(self, video_title):
        try:
            artist, song_name = get_artist_title(video_title)
            spotify_uri = self.get_song_spotify_uri(song_name, artist)

            if spotify_uri != -1:
                return spotify_uri
            else:
                return None
        except:  # TODO fix this pylint broad exception
            # print("Could not find song name and artist from {0}".format(video_title))
            return None

    # get youtube videos from playlist (after timestamp if provided) & returns their spotify id information
    def get_songs_information(self, playlist_id, download, timestamp=None):
        songs = []
        # spotify_ids = []

        request = self.youtube_client.playlistItems().list(
            part="snippet,contentDetails",
            maxResults=50,
            playlistId=playlist_id
        )

        # keep requesting songs from playlist while some are still remaining
        while True:
            response = request.execute()

            for video in response['items']:
                video_title = video["snippet"]["title"]
                published_at_str = video["snippet"]["publishedAt"]
                published_at = parse_youtube_datetime(published_at_str)  # TODO make sure this in UTC
                youtube_url = "https://www.youtube.com/watch?v={}".format(video['contentDetails']['videoId'])

                if not download:
                    # only add song if its been added to playlist after last sync
                    if timestamp is None or published_at > datetime.utcfromtimestamp(timestamp):
                        spotify_id = self.get_spotify_id(video_title)
                        if spotify_id is not None:
                            song = {"spotify_id": spotify_id, "yt_url": youtube_url}
                            songs.append(song)
                else:
                    songs.append({"yt_url": youtube_url, "vid_title": video_title})

            # refine request so it fetches next page of results or prevent anymore requests
            if 'nextPageToken' in response:
                request = self.youtube_client.playlistItems().list(
                    part="snippet,contentDetails",
                    maxResults=50,
                    playlistId=playlist_id,
                    pageToken=response['nextPageToken']
                )
            else:
                break

        return songs

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
            return -1  # TODO replace all -1 with proper error handling
        else:
            return response_json["id"]

    def get_song_spotify_uri(self, song_name, artist):
        q = "{0}+{1}".format(song_name, artist)
        spotify_type = "track"
        market = "GB"
        limit = 1  # TODO: Might cause issue

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

    def add_songs_to_spotify_playlist(self, song_uris, spotify_playlist_id):
        while len(song_uris) > 0:
            batch_size = min(100, len(song_uris))  # N <= 100

            # send first N songs to spotify
            request_data = json.dumps(song_uris[:batch_size])

            # remove first N elements from song_uris
            song_uris = song_uris[batch_size:]

            query = "https://api.spotify.com/v1/playlists/{}/tracks".format(spotify_playlist_id)

            response = requests.post(
                query,
                data=request_data,
                headers={
                    "Authorization": "Bearer {}".format(self.token),
                    "Content-Type": "application/json"
                }
            )

            print(response.json())

    def sync_playlists(self):
        for yt_playlist_id, download in get_inputs().items():
            print(f"syncing: {self.get_playlist_name(yt_playlist_id)}")
            if self.storage.has_playlist_been_synced(yt_playlist_id):
                last_synced = self.storage.get_last_synced_timestamp(yt_playlist_id)
                spotify_id = self.storage.get_spotify_playlist_id(yt_playlist_id)
            else:
                last_synced = None
                playlist_name = self.get_playlist_name(yt_playlist_id)
                spotify_id = self.create_playlist(playlist_name)

            songs = self.get_songs_information(yt_playlist_id, download, last_synced)
            if download:
                # Equivelent to youtube-dl -x --audio-format mp3 --audio-quality 320K "url"
                options = {
                    "outtmpl": f"~/projects/youtube-spotify-sync/dl_dump/%(title)s.%(ext)s",
                    # "outtmpl": f"{self.local_files_path}/%(title)s.%(ext)s",
                    "geo_bypass": True,
                    "postprocessors":
                        [{'key': 'FFmpegExtractAudio',
                          'nopostoverwrites': False,
                          'preferredcodec': 'mp3',
                          'preferredquality': '320'}],
                    "noplaylist": True,
                }
                downloader = youtube_dl.YoutubeDL(options)
                for song in songs:
                    # TODO send email
                    print(f"downloading: {song['vid_tile']}")
                    downloader.download([song["yt_url"]])
            else:
                song_uris = [song["spotify_id"] for song in songs]
                self.add_songs_to_spotify_playlist(song_uris, spotify_id)

            if self.storage.has_playlist_been_synced(yt_playlist_id):
                self.storage.update_last_synced(yt_playlist_id)
            else:
                self.storage.store_new_entry(yt_playlist_id, spotify_id)


# TODO implement as cron job
if __name__ == '__main__':
    cp = CreatePlaylist()
    cp.sync_playlists()
