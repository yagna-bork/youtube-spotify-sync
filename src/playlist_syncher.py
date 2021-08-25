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
from youtube_api import get_youtube_api, VideoInfo
import math
from threading import Thread
from spotify_api import get_spotify_api, SpotifyAPI
import asyncio
import typing as t

sikuli_instruction = t.Tuple[str, int]


class PlaylistSyncher:
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

    def save_instructions_to_file(self, instructions):
        path = f"{self.instructions_dir_path}/{str(datetime.now())}-instructions.txt"
        path = re.sub(" +", "-", path)
        with open(path, "w+") as file:
            file.write("\n".join(instructions))
        return path

    def split_video_into_chapters_and_save(self, file_path: str, chapters: t.List[VideoInfo]) -> t.List[str]:
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

    async def _get_spotify_uris(self, videos: t.List[VideoInfo]) -> t.List[str]:
        uris = []
        for video in videos:
            if artist_title := get_artist_title(video["title"]):
                if uri := await self._spotify_api.get_song_uri(artist_title[0], artist_title[1]):
                    uris.append(uri)
        return uris

    async def sync_playlist(
        self, yt_playlist_id: str, download: bool, sikulix_instructions: t.List[sikuli_instruction]
    ) -> None:
        playlist_name = await self._youtube_api.get_playlist_name(yt_playlist_id)
        print(f"syncing: {playlist_name}")

        if (
            (spotify_id := self.storage.get_spotify_playlist_id(yt_playlist_id))
            and self._spotify_api.does_playlist_exist(spotify_id)
        ):
            last_synced = self.storage.get_last_synced_timestamp(yt_playlist_id)
            name_created_with = self.storage.get_spotify_playlist_name(yt_playlist_id)
        else:
            last_synced = None
            playlist = await self._spotify_api.playlist_create(playlist_name, False)
            spotify_id, name_created_with = playlist.id, playlist.name

        most_recent_sync = datetime.utcnow()
        unsynced_songs = [
            song
            for song in await self._youtube_api.get_video_infos_from_playlist(yt_playlist_id)
            if not last_synced or song["publishedAt"] >= last_synced
        ]
        if download:
            await self._handle_songs_to_download(
                unsynced_songs, name_created_with, sikulix_instructions, self.num_threads
            )
        else:
            if uris := await self._get_spotify_uris(unsynced_songs):
                await self._spotify_api.playlist_add(spotify_id, uris)

        if self.storage.has_playlist_been_synced(yt_playlist_id):
            self.storage.update_last_synced(yt_playlist_id, most_recent_sync)
        else:
            self.storage.store_new_entry(yt_playlist_id, most_recent_sync, spotify_id, name_created_with)

    async def sync_playlists(self) -> None:
        sikulix_instructions = []
        await asyncio.gather(
            *[
                self.sync_playlist(id_, download, sikulix_instructions)
                for id_, download in get_inputs().items()
            ]
        )
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

    async with get_spotify_api() as spotify_api, get_youtube_api() as youtube_api:
        psync = PlaylistSyncher(**kwargs, spotify_api=spotify_api, youtube_api=youtube_api)
        await psync.sync_playlists()

# TODO implement as cron job
# TODO use youtube thumbnail/playlist cover iamge for spotify cover image
if __name__ == '__main__':
    asyncio.run(main())
