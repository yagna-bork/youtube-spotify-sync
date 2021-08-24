import os
from datetime import datetime
import youtube_dl
import re
import sys
from youtube_title_parse import get_artist_title
import subprocess
import eyed3
from storage_manager import StorageManager
from input_manger import get_inputs
from datetime_manager import parse_youtube_datetime
from youtube_api import get_youtube_api
import math
from threading import Thread
from spotify_api import get_spotify_api, SpotifyAPI
import asyncio
import typing as t

sikuli_instruction = t.Tuple[str, int]


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
    def __init__(self, spotify_api: SpotifyAPI, youtube_api, verbose=True, num_threads=5):
        # TODO smart last_synced, check if playlist_id exists on spotify, if not, reset and sync every song again
        self.storage = StorageManager()
        # TODO these three, bottom two with default values
        self.spotify_local_files_path = "{}/Music/spotify".format(os.getenv("HOME"))
        self.downloads_dir_path = "../dl_dump"
        self.instructions_dir_path = "../instruction_logs"
        self.verbose = verbose
        self.num_threads = num_threads
        self.download_archive_path = "../download_archive.txt"
        self._youtube_downloader = youtube_dl.YoutubeDL(
            {
                "outtmpl": f"{self.downloads_dir_path}/%(id)s.%(ext)s",
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
        self._spotify_api = spotify_api
        self._youtube_api = youtube_api

    @staticmethod
    def get_available_videos(playlist_items: t.List[t.Dict[str, t.Any]], youtube_api) -> t.List[t.Dict[str, t.Any]]:
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
    async def get_songs_information(self, youtube_api, playlist_id, download, timestamp=None):
        songs, next_page_token = [], None
        playlist_items = youtube_api.playlistItems()
        request = playlist_items.list(
            part="snippet,contentDetails", maxResults=50, playlistId=playlist_id, pageToken=next_page_token,
        )

        while request is not None:
            response = request.execute()
            videos = self.get_available_videos(response["items"], youtube_api)

            for video in videos:
                video_title = video["snippet"]["title"]
                artist = None
                title = None
                if not download:
                    if not (artist_title := get_artist_title(video_title)):
                        continue
                    artist, title = artist_title
                published_at = parse_youtube_datetime(video["snippet"]["publishedAt"])
                youtube_id = video['contentDetails']['videoId']
                youtube_url = "https://www.youtube.com/watch?v={}".format(youtube_id)

                if timestamp and published_at < datetime.utcfromtimestamp(timestamp):
                    continue
                if not download:
                    if not (spotify_id := await self._spotify_api.get_song_uri(artist, title)):
                        continue
                    song = {"spotify_id": spotify_id, "yt_url": youtube_url}
                    songs.append(song)
                else:
                    chapters = self.parse_chapters_from_description(video["snippet"]["description"])
                    song_info = {
                        "yt_id": youtube_id, "vid_title": video_title, "yt_url": youtube_url, "chapters": chapters
                    }
                    songs.append(song_info)

            request = playlist_items.list_next(request, response)  # pagination
        return songs

    def get_playlist_name(self, playlist_id):
        request = self._youtube_api.playlists().list(
            part="snippet",
            id=playlist_id
        )
        response = request.execute()
        return response['items'][0]['snippet']['title']

    def save_instructions_to_file(self, instructions):
        path = f"{self.instructions_dir_path}/{str(datetime.now())}-instructions.txt"
        path = re.sub(" +", "-", path)
        with open(path, "w+") as file:
            file.write("\n".join(instructions))
        return path

    # TODO Move into Youtube API code
    @staticmethod
    def parse_chapter_information(
        line: str, format_to_use_idx: int = -1
    ) -> t.Optional[t.Tuple[YoutubeChapter, int]]:
        timestamp = r"((\d{1,2}:)?\d{1,2}:\d{1,2})"
        wrapped_ts = (
            rf"((?P<ts1>{timestamp})|\((?P<ts2>{timestamp})\)|\[(?P<ts3>{timestamp})\])"
        )
        seperator = rf"(?P<sep>( +-+ +)|( +\|+ +)|(: +))"
        ts_pattern = re.compile(wrapped_ts)

        if not ts_pattern.search(line):  # need atleast hint of timestamp to carry on
            return

        valid_formats = [
            # 0:00 - title - unrelated link
            re.compile(rf"{wrapped_ts}{seperator}(?P<title>.*?)(?P=sep)"),
            re.compile(rf"{wrapped_ts}{seperator}(?P<title>.*)"),
            # non-space seperators don't work, have to assume last space if the seperator
            # hence this is to be later in order of formats tried
            re.compile(rf"{wrapped_ts} +(?P<title>.*)$"),
            re.compile(rf"(?P<title>.*){seperator}{wrapped_ts}$"),
            re.compile(rf"(?P<title>.*) +{wrapped_ts}$"),
        ]
        valid_formats = valid_formats if format_to_use_idx == -1 else [valid_formats[format_to_use_idx]]
        for idx, format_ in enumerate(valid_formats):
            match = format_.match(line)
            if match:
                timestamp = match.group("ts1") or match.group("ts2") or match.group("ts3")
                title = match.group("title").strip()
                youtube_chapter = YoutubeChapter(YoutubeChapter.start_timestamp_to_seconds(timestamp), title)
                format_used_idx = idx if format_to_use_idx == -1 else format_to_use_idx
                return youtube_chapter, format_used_idx

    @classmethod
    def parse_chapters_from_description(cls, description: str) -> t.List[YoutubeChapter]:
        chapters = []
        lines = description.split("\n")
        parsing_format_to_use_idx = -1
        for line in lines:
            if result := cls.parse_chapter_information(line, parsing_format_to_use_idx):
                youtube_chapter, format_used_idx = result
                if len(chapters) == 0:
                    # youtube rules say first timestamp must start at 0:00 for chapters in description to be valid
                    if youtube_chapter.seconds_after_start != 0:
                        return []
                    else:
                        # using the assumption that only one format per description for optimisation
                        parsing_format_to_use_idx = format_used_idx
                chapters.append(youtube_chapter)
        return chapters

    def split_video_into_chapters_and_save(self, file_path: str, chapters: t.List[YoutubeChapter]) -> t.List[str]:
        song_files = []
        for i, chapter in enumerate(chapters):
            output_file = f"{chapter.title}.mp3"
            ffmpeg_args = [
                "ffmpeg", "-ss", str(chapter.seconds_after_start), "-loglevel",
                "info" if self.verbose else "quiet",
                "-i", file_path, "-b:a", "320k", f"{self.downloads_dir_path}/{output_file}"
            ]
            if i + 1 < len(chapters):
                duration = chapters[i+1].seconds_after_start - chapter.seconds_after_start
                ffmpeg_args = ffmpeg_args[:3] + ["-t", str(duration)] + ffmpeg_args[3:]
            # TODO check if this completed succesfully, only then append to song_files
            subprocess.run(ffmpeg_args)
            song_files.append(output_file)
        return song_files

    @staticmethod
    def add_id3_tag(file_path: str, title: str, album: str, track_number: int) -> None:
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

    @classmethod
    def _get_chunked_urls(cls, urls, num_threads):
        """
        Returns a list of urls in chunked form so the load on each thread is balanced

        Example:
            urls: [1,2,3..35], num_threads: 6
            returns [[1..6],[7..12],[13..18],[19..24],[25..30],[31..35]]

        Example:
            urls: [1,2,3], num_threads: 5
            returns [[1], [2], [3]] -> only 3 threads are needed
        """
        def increment_first_n(n: int, lst: t.List[t.Union[int, float]]) -> None:
            for idx in range(n):
                lst[idx] += 1

        chunk_size = math.floor(len(urls) / num_threads)
        allocation = [chunk_size] * num_threads
        increment_first_n(len(urls) - sum(allocation), allocation)  # ensures sum(allocation) == len(urls)

        chunked_urls, i = [], 0
        for step in allocation:
            if step == 0:
                break
            chunked_urls.append(urls[i: i + step])
            i += step
        return chunked_urls

    # TODO convert to https://docs.python.org/3/library/asyncio-subprocess.html
    def _download_yt_videos_threaded(self, urls: t.List[str], num_threads: int) -> None:
        started_threads = []
        chunked_urls = self._get_chunked_urls(urls, num_threads)
        for urls in chunked_urls:
            thread = Thread(target=self._youtube_downloader.download, kwargs={"url_list": urls})
            thread.start()
            started_threads.append(thread)

        for thread in started_threads:
            thread.join()

    async def _handle_songs_to_download(
        self,
        songs: t.List[t.Dict[str, t.Any]],
        name_created_with: str,
        sikulix_instructions: t.List[sikuli_instruction],
        num_threads: int = 5,
    ) -> None:
        urls = [song["yt_url"] for song in songs]
        # TODO speed up: stop downloading mp4 -> mp3 in every case
        # TODO (WARNING: Requested formats are incompatible for merge and will be merged into mkv.)
        self._download_yt_videos_threaded(urls, num_threads)

        for idx, song in enumerate(songs):
            yt_id, vid_title, chapters = song["yt_id"], song["vid_title"], song["chapters"]
            expected_download_location = os.path.join(self.downloads_dir_path, yt_id + ".mp3")
            if not os.path.isfile(expected_download_location):
                # TODO implement "loose songs" bucket for songs that errored but should be retried
                print(
                    f"Failed to download {vid_title}."
                    f" You will have to do sync it manually until the loose songs feature is implemented"
                )
                continue

            file_name = vid_title + ".mp3"
            file_path = os.path.join(self.downloads_dir_path, file_name)
            os.rename(expected_download_location, file_path)

            if chapters:
                res = await self._spotify_api.playlist_create(vid_title, True)
                playlist = res.name
                downloaded_songs = self.split_video_into_chapters_and_save(file_path, chapters)
                os.remove(file_path)
            else:
                playlist, downloaded_songs = name_created_with, [file_name]

            for i, file_name in enumerate(downloaded_songs):
                title = file_name.rpartition(".mp3")[0]
                path = os.path.join(self.downloads_dir_path, file_name)
                self.add_id3_tag(path, title=title, album=playlist, track_number=i + 1)
                # TODO make sure same ordering (i.e. track number) shows up in local files
                os.rename(path, os.path.join(self.spotify_local_files_path, file_name))

            sikulix_instructions.append((playlist, len(downloaded_songs)))
            print(f"{playlist}: {idx + 1}/{len(songs)} songs synced successfully")

    async def sync_playlists(self):
        sikulix_instructions = []
        # TODO asyncio this whole thing to benefit from async spotify & youtube calls
        for yt_playlist_id, download in get_inputs().items():
            playlist_name = self.get_playlist_name(yt_playlist_id)
            print(f"syncing: {playlist_name}")
            if self.storage.has_playlist_been_synced(yt_playlist_id):
                last_synced = self.storage.get_last_synced_timestamp(yt_playlist_id)
                spotify_id = self.storage.get_spotify_playlist_id(yt_playlist_id),
                name_created_with = self.storage.get_spotify_playlist_name(yt_playlist_id)
            else:
                last_synced = None
                playlist = await self._spotify_api.playlist_create(playlist_name, False)
                spotify_id, name_created_with = playlist.id, playlist.name

            songs = await self.get_songs_information(self._youtube_api, yt_playlist_id, download, last_synced)
            if download:
                await self._handle_songs_to_download(songs, name_created_with, sikulix_instructions, self.num_threads)
            else:
                song_uris = [song["spotify_id"] for song in songs]
                if song_uris:
                    await self._spotify_api.playlist_add(spotify_id, song_uris)

            if self.storage.has_playlist_been_synced(yt_playlist_id):
                self.storage.update_last_synced(yt_playlist_id)
            else:
                self.storage.store_new_entry(yt_playlist_id, spotify_id, name_created_with)

        if sikulix_instructions:
            proceed = input(
                "Would you like to automatially add the downloaded songs to their respective spotify playlists?\n"
                "If you wish to proceed, please disable any applications that can reverse the scroll direction\n"
                "for a mouse, not trackpad. (Y/n): "
            )
            if proceed.lower() == "y":
                self.add_songs_to_playlists_sikulix(sikulix_instructions)


async def main() -> None:
    verbose_arg = any(arg in ["--verbose", "-v"] for arg in sys.argv)
    kwargs = {"verbose": verbose_arg}
    if any(arg == "-n" for arg in sys.argv):
        num_threads_arg = sys.argv[sys.argv.index("-n") + 1]
        kwargs["num_threads"] = num_threads_arg

    with get_youtube_api() as youtube_api:
        async with get_spotify_api() as spotify_api:
            cp = CreatePlaylist(**kwargs, spotify_api=spotify_api, youtube_api=youtube_api)
            await cp.sync_playlists()

# TODO implement as cron job
# TODO use youtube thumbnail/playlist cover iamge for spotify cover image
if __name__ == '__main__':
    asyncio.run(main())
