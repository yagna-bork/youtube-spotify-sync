import requests
import json
import os

from secrets import user_id, get_uri, redirect_url

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

import youtube_dl

class CreatePlaylist:
    def __init__(self):
        self.user_id = user_id
        # self.token = self.get_spotify_token()
        self.token = "BQDK99OHx4Mq6z_UqblJGl5u8255m2KwswFwnwpSojycVNX0FCVRyTw4WqUE9J8Wpq8IsSnp0jStBWpNLqSfZKnVUcIL2CqgMIHXIsJceIg1GPLssqXXIL4k6InE2nj15dsuNyZBfvVaCCU4JykxtaTExjBB4z80MLvikbq505ogf6VMXIOPL6rekMzSE_BH3qxtqSve3g"
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
        request = self.youtube_client.playlistItems().list(
            part="snippet,contentDetails",
            maxResults=50,
            # id of my personal liked videos playlist
            # TODO identify this id automatically
            playlistId="LLEA6rXRPPbQur1xyOgurtQg"
        )
        response = request.execute()

        print("Length of liked videos: {}".format(len(response['items'])))

        # only using youtube-dl for first video which worked on example repo
        item = response['items'][0]
        video_title = item["snippet"]["title"]
        youtube_url = "https://www.youtube.com/watch?v={}".format(item['contentDetails']['videoId'])
        video = youtube_dl.YoutubeDL({}).extract_info(youtube_url, False)
        song_name = video['track']
        artist = video['artist']
        print("Youtube url: {0}"
              "\nTitle: {5}"
              "Item object: "
              "\n{1}"
              "\nSong name{2}"
              "\nArtist: {3}"
              "\nYT-DL object:"
              "\n{4}".format(youtube_url, item, song_name, artist, video, video_title))

        # for item in response['items']:
        #     video_title = item["snippet"]["title"]
        #     youtube_url = "https://www.youtube.com/watch?v={}".format(item['contentDetails']['videoId'])
        #
        #     try:
        #         # use youtube to parse song information
        #         video = youtube_dl.YoutubeDL({}).extract_info(youtube_url, False)
        #
        #         if 'track' in video:
        #             print("track attribute found for {}".format(youtube_url))
        #         if 'artist' in video:
        #             print("video attribute found for {}".format(youtube_url))
        #
        #         song_name = video['track']
        #         artist = video['artist']
        #
        #         print("Information for {0}\nSong title: {1}\nArtist: {2}\n".format(
        #             video_title, song_name, artist))
        #
        #         if song_name is not None and artist is not None:
        #             print("SONG NAME: {0}, ARTIST: {1} PASSED IF CHECK".format(song_name, artist))
        #
        #             # save information
        #             self.liked_songs_info[video_title] = {
        #                 "youtube_url": youtube_url,
        #                 "song_name": song_name,
        #                 "artist": artist,
        #
        #                 # spotify resource uri for easy access
        #                 "spotify_uri": self.get_song_spotify_uri(song_name, artist)
        #             }
        #     except:
        #         print("{} can no longer be accessed.".format(youtube_url))


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

        # uri of first song from query results
        # print(response_json)
        return response_json['tracks']['items'][0]['uri']

    def add_songs_to_playlist(self): #TODO timestamp so only new entries added
        self.get_liked_videos()
        song_uris = [info['spotify_uri'] for _, info in self.liked_songs_info.items()]
        new_playlist_id = self.create_playlist()

        request_data = json.dumps(song_uris)

        query = "https://api.spotify.com/v1/playlists/{}/tracks".format(new_playlist_id)

        # position left empty -> songs appended
        # request_body = json.dumps({
        #     "uris": request_data
        # })

        response = requests.post(
            query,
            data=request_data,
            headers={
                "Authorization": "Bearer {}".format(self.token),
                "Content-Type": "application/json"
            }
        )

        return response.json()

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


if __name__ == '__main__':
    cp = CreatePlaylist()
    # print(cp.add_songs_to_playlist())
    cp.get_liked_videos()
    print(cp.liked_songs_info)
