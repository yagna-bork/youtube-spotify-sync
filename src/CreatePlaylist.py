import requests
import json
import os
from datetime import datetime
import youtube_dl
import typing as t
import re
import sys
import glob
import google_auth_oauthlib.flow
import google.oauth2.credentials
import google.auth.transport.requests
import google.auth.exceptions
import googleapiclient.discovery
import googleapiclient.errors
from youtube_title_parse import get_artist_title
import subprocess
import secrets
import eyed3
from storage_manager import StorageManager
from input_manger import get_inputs
from datetime_manager import parse_youtube_datetime
import keyring
import pkce


class APIHelper:
    def __init__(self) -> None:
        self._keyring_service_id = "yt2spotifysync"

    def store_kvp(self, key: str, value: str) -> None:
        keyring.set_password(self._keyring_service_id, key, value)

    def retrieve_kvp(self, key: str) -> str:
        return keyring.get_password(self._keyring_service_id, key)

    def _do_google_auth_flow(self, scopes: t.List[str]) -> google.oauth2.credentials.Credentials:
        secrets_file = "client_secret.json"
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(secrets_file, scopes)
        return flow.run_console()

    def _build_credentials(self, credentials_json: str) -> google.oauth2.credentials.Credentials:
        credentials_dict = json.loads(credentials_json)
        return google.oauth2.credentials.Credentials.from_authorized_user_info(credentials_dict)

    def _get_google_apis_credentials(self, scopes: t.List[str]) -> google.oauth2.credentials.Credentials:
        credentials_json = self.retrieve_kvp("credentials_json")
        if credentials_json:
            credentials = self._build_credentials(credentials_json)
            if credentials.valid:
                return credentials
            else:
                try:
                    request = google.auth.transport.requests.Request()
                    credentials.refresh(request)
                except google.auth.exceptions.RefreshError:
                    print("Something went wrong with refreshing your google access token. Let's make a new one.")
                else:
                    self.store_kvp("credentials_json", credentials.to_json())
                    return credentials

        credentials = self._do_google_auth_flow(scopes)
        credentials_json = credentials.to_json()
        self.store_kvp("credentials_json", credentials_json)
        return credentials

    @property
    def youtube_api(self):
        scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
        credentials = self._get_google_apis_credentials(scopes)
        return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

    def _get_spotify_auth_url(self, scopes: t.List[str]) -> t.Tuple[str, str, str]:
        code_verifier, code_challenge = pkce.generate_pkce_pair()
        with open("spotify_auth.json", "r") as auth_data_file:
            auth_data = json.load(auth_data_file)
        url = auth_data["url"]
        state = secrets.token_urlsafe(256)
        query_params_dict = {
            "client_id": auth_data["client_id"],
            "reponse_type": "code",
            "redirect_url": "localhost:8080",
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
            "state": state,
            "scopes": scopes,
        }
        query_params = ",".join([f"{name}={val}" for name, val in query_params_dict.items()])
        return f"{url}?{query_params}", code_verifier, state

    def _collect_redirect(self) -> t.Dict[str, str]:
        return

    def _do_spotify_auth_pkce_flow(self, scopes: t.List[str]):
        url, code_verifier, state = self._get_spotify_auth_url(scopes)
        print("Please go to this url to allow this app to create and manage your playlists: " + url)
        response = self._collect_redirect()
        if response.get("error"):
            return
        auth_code, resp_state = response.values()
        if state != resp_state:
            return

    @property
    def spotify_api(self):
        pass


class YoutubeChapter(t.NamedTuple):
    seconds_after_start: int
    title: str

    @staticmethod
    def start_timestamp_to_seconds(start_timestamp: str):
        start_timestamp_list = list(map(int, start_timestamp.split(":")))
        while len(start_timestamp_list) < 3:
            start_timestamp_list.insert(0, 0)
        start_timestamp_list.reverse()  # [seconds, mins, hours]

        start_seconds = 0
        for i in range(len(start_timestamp_list)):
            start_seconds += start_timestamp_list[i] * 60**i
        return start_seconds


class CreatePlaylist:
    def __init__(self, verbose=True, fetch_token=False):
        self.user_id = secrets.user_id
        self.api_helper = APIHelper()
        self.liked_songs_info = {}
        self.storage = StorageManager()
        self.spotify_local_files_path = "{}/Music/spotify".format(os.getenv("HOME"))
        self.downloads_dir_path = "../dl_dump"
        self.instructions_dir_path = "../instruction_logs"
        self.verbose = verbose

    @staticmethod
    def get_spotify_token():
        print("Access this uri for spotify authorization:\n{}".format(secrets.get_uri))
        code = input("Enter the code you got back: ")
        curl_cmd = "curl -H 'Authorization: Basic {0}' " \
                   "-d grant_type=authorization_code " \
                   "-d code={2} " \
                   "-d redirect_uri={1} " \
                   "https://accounts.spotify.com/api/token".format(secrets.base64_id_secret, secrets.redirect_url, code)
        print("Use this curl command:\n{}".format(curl_cmd))
        spotify_token = input("Enter the spotify token: ")
        return spotify_token

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
        except Exception:  # TODO fix this pylint broad exception
            # print("Could not find song name and artist from {0}".format(video_title))
            return None

    # get youtube videos from playlist (after timestamp if provided) & returns their spotify id information
    def get_songs_information(self, playlist_id, download, timestamp=None):
        songs = []
        next_page_token = None
        # keep requesting songs from playlist while some are still remaining
        while True:
            with self.api_helper.youtube_api as youtube_api:
                request = youtube_api.playlistItems().list(
                    part="snippet,contentDetails",
                    maxResults=50,
                    playlistId=playlist_id,
                    pageToken=next_page_token,
                )
                response = request.execute()
            for video in response['items']:
                video_title = video["snippet"]["title"]
                published_at_str = video["snippet"]["publishedAt"]
                published_at = parse_youtube_datetime(published_at_str)  # TODO make sure this in UTC
                youtube_url = "https://www.youtube.com/watch?v={}".format(video['contentDetails']['videoId'])
                # only add song if its been added to playlist after last sync
                if timestamp is None or published_at > datetime.utcfromtimestamp(timestamp):
                    if not download:
                        spotify_id = self.get_spotify_id(video_title)
                        if spotify_id is not None:
                            song = {"spotify_id": spotify_id, "yt_url": youtube_url}
                            songs.append(song)
                    else:
                        chapters = self.parse_chapters_from_description(video["snippet"]["description"])
                        song_info = {"yt_url": youtube_url, "vid_title": video_title, "chapters": chapters}
                        songs.append(song_info)
            # refine request so it fetches next page of results or prevent anymore requests
            if 'nextPageToken' in response:
                next_page_token = response['nextPageToken']
            else:
                break
        return songs

    def get_playlist_name(self, playlist_id):
        with self.api_helper.youtube_api as youtube_api:
            request = youtube_api.playlists().list(
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
            return response_json["id"], response_json["name"]

    @staticmethod
    def parse_query(*args: str) -> str:
        query = ""
        for arg in args:
            no_whitespace_ascii_arg = re.sub(r"[^0-9A-Za-z ]| +$|^ +", "", arg)
            no_space_arg = re.sub(" +", "+", no_whitespace_ascii_arg)
            formatted_arg = f"{no_space_arg}+" if no_space_arg[:-1] != "+" else no_space_arg
            query += formatted_arg
        return query

    def get_song_spotify_uri(self, song_name, artist):
        q = self.parse_query(song_name, artist)
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

    def save_instructions_to_file(self, instructions):
        # TODO send email
        path = f"{self.instructions_dir_path}/{str(datetime.now())}-instructions.txt"
        path = re.sub(" +", "-", path)
        with open(path, "w+") as file:
            file.write("\n".join(instructions))
        return path

    @staticmethod
    def parse_chapter_information(
        line: str, format_to_use_idx: int = -1
    ) -> t.Optional[t.Tuple[YoutubeChapter, int]]:
        timestamp = r"(\d{1,2}:)?\d{1,2}:\d{1,2}"
        wrapped_ts = rf"({timestamp})|(\({timestamp}\)|(\[{timestamp}\]))"
        seperator = rf"( +-+ +)|( +\|+ +)|(: +)"
        ts_pattern = re.compile(wrapped_ts)

        if not ts_pattern.search(line):  # need atleast hint of timestamp to carry on
            return

        valid_formats = [
            # 0:00 - title - unrelated link
            re.compile(rf"(?P<wrapped_ts>{wrapped_ts})(?P<sep>{seperator})(?P<title>.*?)(?P=sep)"),
            re.compile(rf"(?P<wrapped_ts>{wrapped_ts})({seperator})(?P<title>.*)"),
            # non-space seperators don't work, have to assume last space if the seperator
            # hence this is to be later in order of formats tried
            re.compile(rf"(?P<wrapped_ts>{wrapped_ts}) +(?P<title>.*)$"),
            re.compile(rf"(?P<title>.*)({seperator})(?P<wrapped_ts>{wrapped_ts})$"),
            re.compile(rf"(?P<title>.*) +(?P<wrapped_ts>{wrapped_ts})$"),
        ]
        # using one format per description assumption for optimisation
        valid_formats = valid_formats if format_to_use_idx == -1 else [valid_formats[format_to_use_idx]]
        for idx, format_ in enumerate(valid_formats):
            match = format_.match(line)
            if match:
                wrapped_ts, title = match.group("wrapped_ts"), match.group("title").strip()
                unwrapped_ts = ts_pattern.search(wrapped_ts).group(0)
                youtube_chapter = YoutubeChapter(YoutubeChapter.start_timestamp_to_seconds(unwrapped_ts), title)
                format_used_idx = idx if format_to_use_idx == -1 else format_to_use_idx
                return youtube_chapter, format_used_idx

    def parse_chapters_from_description(self, description: str) -> t.List[YoutubeChapter]:
        chapters = []
        lines = description.split("\n")
        parsing_format_to_use_idx = -1
        for line in lines:
            parsing_result = self.parse_chapter_information(line, parsing_format_to_use_idx)
            if parsing_result:
                youtube_chapter, format_used_idx = parsing_result
                if len(chapters) == 0:
                    # youtube rules say first timestamp must start at 0:00 for chapters in description to be valid
                    if youtube_chapter.seconds_after_start != 0:
                        return []
                    else:
                        parsing_format_to_use_idx = format_used_idx
                chapters.append(youtube_chapter)
        return chapters

    # TODO add video_title as metadata for individual songs
    def split_video_into_chapters(self, full_video_file: str, chapters: t.List[YoutubeChapter]) -> t.List[str]:
        song_files = []
        for i, chapter in enumerate(chapters):
            output_file = f"{chapter.title}.mp3"
            ffmpeg_args = [
                "ffmpeg",
                "-ss",
                str(chapter.seconds_after_start),
                "-loglevel",
                "info" if self.verbose else "quiet",
                "-i",
                f"{self.downloads_dir_path}/{full_video_file}",
                "-b:a",
                "320k",
                f"{self.downloads_dir_path}/{output_file}"
            ]
            if i + 1 < len(chapters):
                duration = chapters[i+1].seconds_after_start - chapter.seconds_after_start
                ffmpeg_args = ffmpeg_args[:3] + ["-t", str(duration)] + ffmpeg_args[3:]
            subprocess.run(ffmpeg_args)
            song_files.append(output_file)
        return song_files

    def add_id3_tag(self, file_path: str, title: str, album: str, track_number: int) -> None:
        file = eyed3.load(file_path)
        file.tag.title = title
        file.tag.album = album
        file.tag.track_number = track_number
        file.tag.save()

    def handle_instruction(self, instruction, instructions_list):
        instructions_list.append(instruction)
        # only show instructions during slient mode, otherwise it will get drowned out by youtube_dl output
        if not self.verbose:
            print(instruction)

    def _handle_songs_to_download(self, songs, download_instructions, name_created_with) -> None:
        downloader = youtube_dl.YoutubeDL(
            {
                "outtmpl": f"/Users/yaggy/programming/automation/ytToSpotify/dl_dump/%(title)s.%(ext)s",
                "geo_bypass": True,
                "postprocessors":
                    [{'key': 'FFmpegExtractAudio',
                      'nopostoverwrites': False,
                      'preferredcodec': 'mp3',
                      'preferredquality': '320'}],
                "noplaylist": True,
                "quiet": not self.verbose,
                "no_warnings": not self.verbose,
            }
        )
        for song in songs:
            yt_url, chapters = song["yt_url"], song["chapters"]
            # TODO speed up: stop downloading mp4 -> mp3 in every case
            # (WARNING: Requested formats are incompatible for merge and will be merged into mkv.)
            downloader.download([yt_url])
            files = glob.glob('../dl_dump/*.mp3')
            vid_file = max(files, key=os.path.getctime).split("/")[-1]  # get most recently created file's name
            vid_title = vid_file.split(".")[0]

            if chapters:
                _, playlist = self.create_playlist(vid_title)
                self.handle_instruction(
                    f"Turn on download option for the '{playlist}' playlist", download_instructions
                )
                # noinspection PyTypeChecker
                downloaded_songs = self.split_video_into_chapters(vid_file, chapters)
                os.remove(f"{self.downloads_dir_path}/{vid_file}")
            else:
                playlist, downloaded_songs = name_created_with, [vid_file]

            for track_number, song_file in enumerate(downloaded_songs):
                song_name, song_path = re.sub(".mp3", "", song_file), f"{self.downloads_dir_path}/{song_file}"
                self.add_id3_tag(song_path, song_name, playlist, track_number)
                os.rename(
                    f"{self.downloads_dir_path}/{song_file}", f"{self.spotify_local_files_path}/{song_file}"
                )
                self.handle_instruction(
                    f"Move {song_name} -> '{playlist}' spotify playlist", download_instructions
                )

    def sync_playlists(self):
        download_instructions = []
        for yt_playlist_id, download in get_inputs().items():
            print(f"syncing: {self.get_playlist_name(yt_playlist_id)}")
            if self.storage.has_playlist_been_synced(yt_playlist_id):
                last_synced = self.storage.get_last_synced_timestamp(yt_playlist_id)
                spotify_id, name_created_with = (
                    self.storage.get_spotify_playlist_id(yt_playlist_id),
                    self.storage.get_spotify_playlist_name(yt_playlist_id)
                )
            else:
                last_synced = None
                playlist_name = self.get_playlist_name(yt_playlist_id)
                spotify_id, name_created_with = self.create_playlist(playlist_name)
                if download:
                    self.handle_instruction(
                        f"Turn on download option for the '{name_created_with}' playlist", download_instructions
                    )

            songs = self.get_songs_information(yt_playlist_id, download, last_synced)
            # todo leaks, teeway (liked songs), all playlists
            if download:
                self._handle_songs_to_download(songs)
            else:
                song_uris = [song["spotify_id"] for song in songs]
                self.add_songs_to_spotify_playlist(song_uris, spotify_id)

            if self.storage.has_playlist_been_synced(yt_playlist_id):
                self.storage.update_last_synced(yt_playlist_id)
            else:
                self.storage.store_new_entry(yt_playlist_id, spotify_id, name_created_with)

        if download_instructions:
            file = self.save_instructions_to_file(download_instructions)
            print(f"You can find all instructions for your local files in {file}")


# TODO implement as cron job
if __name__ == '__main__':
    verbose_arg = any(arg in ["--verbose", "-v"] for arg in sys.argv)
    fetch_token_arg = any(arg in ["--fetch-token", "-f"] for arg in sys.argv)
    cp = CreatePlaylist(verbose=verbose_arg, fetch_token=fetch_token_arg)
    # cp.sync_playlists()
    print(cp.get_playlist_name("PLucKeiEo64s-ldaDEIOutsulqUIsOOpX4"))
