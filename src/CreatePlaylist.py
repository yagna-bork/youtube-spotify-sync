import os
from datetime import datetime
import youtube_dl
import typing as t
import re
import sys
import glob
from youtube_title_parse import get_artist_title
import subprocess
import eyed3
from storage_manager import StorageManager
from input_manger import get_inputs
from datetime_manager import parse_youtube_datetime
from spotipy.client import SpotifyException
from api_helpers import *


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


# TODO refactor to not be a class
class CreatePlaylist:
    def __init__(self, verbose=True):
        # TODO smart last_synced, check if playlist_id exists on spotify, if not, reset and sync every song again
        self.storage = StorageManager()
        # TODO these three, bottom two with default values
        self.spotify_local_files_path = "{}/Music/spotify".format(os.getenv("HOME"))
        self.downloads_dir_path = "../dl_dump"
        self.instructions_dir_path = "../instruction_logs"
        self.verbose = verbose

    # TODO remove this
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

    def get_available_videos(
        self, playlist_items: t.List[t.Dict[str, t.Any]], youtube_api
    ) -> t.List[t.Dict[str, t.Any]]:
        id_to_video = {
            item["contentDetails"]["videoId"]: item for item in playlist_items
        }
        playlist_vid_ids = ",".join(id_to_video.keys())
        available_videos = youtube_api.videos().list(
            part="id,status", maxResults=50, id=playlist_vid_ids,
        ).execute().get("items", [])
        available_video_ids = set([vid["id"] for vid in available_videos])

        return [video for vid_id, video in id_to_video.items() if vid_id in available_video_ids]

    # get youtube videos from playlist (after timestamp if provided) & returns their spotify id information
    def get_songs_information(self, playlist_id, download, timestamp=None):
        songs, next_page_token = [], None

        while True:
            with get_youtube_api() as youtube_api:
                response = youtube_api.playlistItems().list(
                    part="snippet,contentDetails", maxResults=50, playlistId=playlist_id, pageToken=next_page_token,
                ).execute()
                videos = self.get_available_videos(response["items"], youtube_api)
                next_page_token = response.get("nextPageToken")

            for video in videos:
                video_title = video["snippet"]["title"]
                published_at_str = video["snippet"]["publishedAt"]
                published_at = parse_youtube_datetime(published_at_str)  # TODO make sure this in UTC
                youtube_url = "https://www.youtube.com/watch?v={}".format(video['contentDetails']['videoId'])

                if timestamp and published_at < datetime.utcfromtimestamp(timestamp):
                    continue
                if not download and (spotify_id := self.get_spotify_id(video_title)):
                    song = {"spotify_id": spotify_id, "yt_url": youtube_url}
                    songs.append(song)
                else:
                    chapters = self.parse_chapters_from_description(video["snippet"]["description"])
                    song_info = {"yt_url": youtube_url, "vid_title": video_title, "chapters": chapters}
                    songs.append(song_info)

            if not next_page_token:
                break

        return songs

    def get_playlist_name(self, playlist_id):
        with get_youtube_api() as youtube_api:
            request = youtube_api.playlists().list(
                part="snippet",
                id=playlist_id
            )
            response = request.execute()
        return response['items'][0]['snippet']['title']

    # Create corresponding playlist on Spotify
    def create_playlist(self, name, public=True):
        description = "Spotify synced version of the {} playlist from your YouTube".format(name)
        with get_spotify_api() as sp:
            user_id = sp.current_user()['id']
            try:
                result = sp.user_playlist_create(user_id, name=name, public=public, description=description)
                return result["id"], result["name"]
            except SpotifyException as error:
                print(f"Got an error while trying to create playlist: {name}.\n{error}")
                return None

    # TODO Use new version of youtube-dl that implements this fix
    def get_spotify_id(self, video_title):
        artist, song_name = get_artist_title(video_title)
        query = "+".join(artist.split() + song_name.split())
        spotify_id = None
        with get_spotify_api() as sp:
            try:
                result = sp.search(query, limit=1, type="track", market="GB")
                items = result['tracks']['items']
                spotify_id = items[0]['uri'] if items else None
            except SpotifyException as error:
                print(
                    "Got error while trying to get spotify_uri for {0}. song_name, artist: {1}, {2}.\n{3}" .format(
                        video_title, artist, song_name, error
                    )
                )

        # TODO suggest alternative for failed songs command line feature
        return spotify_id

    def add_songs_to_spotify_playlist(self, song_uris, spotify_playlist_id):
        with get_spotify_api() as sp:
            for i in range(0, len(song_uris), 100):
                uris_batch = song_uris[i: i+100]
                try:
                    sp.playlist_add_items(spotify_playlist_id, uris_batch)
                except SpotifyException as error:
                    print(
                        f"Got an error while trying to add following song uris to {spotify_playlist_id}:\n{uris_batch}"
                        f"\n{error}"
                    )

    def save_instructions_to_file(self, instructions):
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
    def split_video_into_chapters_and_save(self, full_video_file: str, chapters: t.List[YoutubeChapter]) -> t.List[str]:
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
            # TODO check if this completed succesfully, only then append to song_files
            subprocess.run(ffmpeg_args)
            song_files.append(output_file)
        return song_files

    def add_id3_tag(self, file_path: str, title: str, album: str, track_number: int) -> None:
        file = eyed3.load(file_path)
        file.tag.title = title
        file.tag.album = album
        file.tag.track_number = track_number
        file.tag.save()

    @classmethod
    def add_songs_to_playlists_sikulix(cls, instructions):
        home = os.environ["HOME"]
        call_args = [
            "java", "-jar", f"{home}/sikulix/sikulixide-2.0.4.jar", "-r",
            f"{home}/programming/automation/ytToSpotify/src/local_files_automation.sikuli/", "--"
        ]
        for playlist, count in instructions:
            call_args.extend(["-e", f"{playlist},{count}"])
        subprocess.run(call_args)

    def _handle_songs_to_download(self, songs, name_created_with, sikulix_instructions) -> None:
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
        for idx, song in enumerate(songs):
            yt_url, chapters = song["yt_url"], song["chapters"]

            # get most recently created file's name
            # TODO speed up: stop downloading mp4 -> mp3 in every case
            # TODO (WARNING: Requested formats are incompatible for merge and will be merged into mkv.)
            downloader.download([yt_url])
            files = glob.glob("../dl_dump/*.mp3")
            vid_file = max(files, key=os.path.getctime).split("/")[-1]  # get most recently created file's name
            vid_title = vid_file.rpartition(".mp3")[0]

            if chapters:
                if not (result := self.create_playlist(vid_title)):
                    print(f"Skipping {vid_title}. Couldn't create the playlist required")
                    continue
                _, playlist = result
                # noinspection PyTypeChecker
                downloaded_songs = self.split_video_into_chapters_and_save(vid_file, chapters)
                os.remove(f"{self.downloads_dir_path}/{vid_file}")
            else:
                playlist, downloaded_songs = name_created_with, [vid_file]

            for track_number, song_file in enumerate(downloaded_songs):
                song_name = re.sub(".mp3", "", song_file)
                song_path = f"{self.downloads_dir_path}/{song_file}"
                self.add_id3_tag(song_path, song_name, playlist, track_number + 1)
                os.rename(song_path, f"{self.spotify_local_files_path}/{song_file}")
                sikulix_instructions.append((playlist, len(downloaded_songs)))

            print(f"{playlist}: {idx + 1}/{len(songs)} songs synced successfully")

    def sync_playlists(self):
        sikulix_instructions = []
        for yt_playlist_id, download in get_inputs().items():
            print(f"syncing: {self.get_playlist_name(yt_playlist_id)}")
            if self.storage.has_playlist_been_synced(yt_playlist_id):
                last_synced = self.storage.get_last_synced_timestamp(yt_playlist_id)
                spotify_id = self.storage.get_spotify_playlist_id(yt_playlist_id),
                name_created_with = self.storage.get_spotify_playlist_name(yt_playlist_id)
            else:
                last_synced = None
                playlist_name = self.get_playlist_name(yt_playlist_id)
                if not (result := self.create_playlist(playlist_name)):
                    print(f"Skipping {playlist_name}. Couldn't create the playlist on spotify")
                    continue
                spotify_id, name_created_with = result

            songs = self.get_songs_information(yt_playlist_id, download, last_synced)
            if download:
                self._handle_songs_to_download(songs, name_created_with, sikulix_instructions)
            else:
                song_uris = [song["spotify_id"] for song in songs]
                self.add_songs_to_spotify_playlist(song_uris, spotify_id)

            if self.storage.has_playlist_been_synced(yt_playlist_id):
                self.storage.update_last_synced(yt_playlist_id)
            else:
                self.storage.store_new_entry(yt_playlist_id, spotify_id, name_created_with)

        if sikulix_instructions:
            proceed = input(
                "Would you like to automatially add the downloaded songs to their respective spotify playlists? (Y/n): "
            )
            if proceed.lower() == "y":
                self.add_songs_to_playlists_sikulix(sikulix_instructions)


# TODO implement as cron job
if __name__ == '__main__':
    verbose_arg = any(arg in ["--verbose", "-v"] for arg in sys.argv)
    cp = CreatePlaylist(verbose=verbose_arg)
    cp.sync_playlists()
