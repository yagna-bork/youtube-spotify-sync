import os
from datetime import datetime
from youtube_title_parse import get_artist_title
import subprocess
from storage_manager import StorageManager
from input_manger import get_inputs
from youtube_api import get_youtube_api, VideoInfo, YoutubeAPI, YoutubeChapter
from spotify_api import get_spotify_api, SpotifyAPI
import asyncio
import typing as t
import argparse
from pathlib import Path
from utils import run_command_async
import eyed3
from shlex import quote

DOWNLOADS_DIR_PATH = Path(__file__).parent.parent / "dl_dump"

SikuliInstructions = t.List[t.Tuple[str, int]]


class PlaylistSyncher:
    def __init__(
        self,
        spotify_api: SpotifyAPI,
        youtube_api: YoutubeAPI,
        verbose: bool = True,
        max_parallel_downloads: int = 5,
        local_files_path: t.Optional[Path] = None,
    ):
        """You must use get_instance instead."""
        self._storage = StorageManager()
        self.spotify_local_files_path = local_files_path
        self.verbose = verbose
        self.max_parallel_downloads = max_parallel_downloads
        self._spotify_api = spotify_api
        self._youtube_api = youtube_api
        self._download_sem = asyncio.Semaphore(max_parallel_downloads)
        self._ffmpeg_lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls, *args, **kwargs) -> "PlaylistSyncher":
        """
        Use this instead of the constructor to get an instance of PlaylistSyncher.

        An instance of PlaylistSyncher must be created in the same asyncio loop that it's methods will be called from.
        This is because the asyncio semaphores are used internally are initialised in the constructor. See __init__
        for the args and kwargs that this method takes.
        """
        return cls(*args, **kwargs)

    async def _split_video_into_chapters(self, file_path: str, chapters: t.List[YoutubeChapter]) -> t.List[str]:
        song_files = []
        for i, chapter in enumerate(chapters):
            output_file = f"{chapter.title}.mp3"
            duration = None
            if i + 1 < len(chapters):
                duration = chapters[i+1].seconds_after_start - chapter.seconds_after_start
            cmd = (
                f"ffmpeg -ss {chapter.seconds_after_start} "
                f"{'-t ' + str(duration) if duration else ''} "
                f"-loglevel {'info' if self.verbose else 'quiet'} "
                f"-i {quote(file_path)} {quote(str(DOWNLOADS_DIR_PATH/output_file))}"
            )
            if await run_command_async(cmd):
                song_files.append(output_file)
        return song_files

    @staticmethod
    def _add_id3_tag(path: Path, title: str, album: str, track_number: int) -> None:
        file = eyed3.load(path)
        file.tag.title = title
        file.tag.album = album
        file.tag.track_number = track_number
        file.tag.save()

    async def _handle_songs_to_download(
        self,
        songs: t.List[VideoInfo],
        name_created_with: str,
        sikulix_instructions: SikuliInstructions,
    ) -> None:
        for idx, song in enumerate(songs):
            youtube_id, title, chapters = song["id"], song["title"], song["chapters"]
            async with self._download_sem:
                # title in youtube-dl output template and on the actual youtube video can vary so id is required
                success = await run_command_async(
                    "youtube-dl --geo-bypass -f 'bestaudio[ext=mp3]/bestaudio' -x --audio-format mp3 --audio-quality 0 "
                    f"-o '{DOWNLOADS_DIR_PATH}/%(id)s.%(ext)s'"
                    f"{'-q --no-warnings' if not self.verbose else ''} "
                    f"{song['url']}"
                )
            if not success:
                # TODO implement "loose songs" bucket for songs that errored but should be retried
                print(
                    f"Failed to download {title}. "
                    f"You will have to do sync it manually until the loose songs feature is implemented"
                )
                continue

            file = f"{title}.mp3"
            full_path = Path(DOWNLOADS_DIR_PATH) / file
            os.rename(Path(DOWNLOADS_DIR_PATH) / f"{youtube_id}.mp3", full_path)

            if chapters:
                await self._spotify_api.playlist_create(title, public=True)
                playlist = title
                async with self._ffmpeg_lock:
                    downloaded_songs = await self._split_video_into_chapters(str(full_path), chapters)
                os.remove(full_path)
            else:
                playlist, downloaded_songs = name_created_with, [file]

            for i, file in enumerate(downloaded_songs):
                full_path = Path(DOWNLOADS_DIR_PATH) / file
                title = file.rpartition(".mp3")[0]
                self._add_id3_tag(full_path, title=title, album=playlist, track_number=i + 1)
                # TODO make sure same ordering (i.e. track number) shows up in local files
                os.rename(full_path, self.spotify_local_files_path / file)

            sikulix_instructions.append((playlist, len(downloaded_songs)))
            print(f"{playlist}: {idx + 1}/{len(songs)} songs synced successfully")

    async def _add_songs_to_spotify_playlist(self, playlist_id: str, songs: t.List[VideoInfo]) -> None:
        if not songs:
            return
        uris = []
        for song in songs:
            if not (artist_title := get_artist_title(song["title"])):
                continue
            if uri := await self._spotify_api.get_song_uri(*artist_title):
                uris.append(uri)
        if uris:
            await self._spotify_api.playlist_add(playlist_id, uris)

    async def _sync_playlist(
        self,
        yt_playlist_id: str,
        download: bool,
        sikulix_instructions: SikuliInstructions,
    ) -> None:
        playlist_name = await self._youtube_api.get_playlist_name(yt_playlist_id)
        print(f"Syncing: {playlist_name}.")

        if (
            (spotify_id := self._storage.get_spotify_playlist_id(yt_playlist_id))
            and self._spotify_api.does_playlist_exist(spotify_id)
        ):
            last_synced = self._storage.get_last_synced_timestamp(yt_playlist_id)
            name_created_with = self._storage.get_spotify_playlist_name(yt_playlist_id)
        else:
            last_synced = None
            playlist = await self._spotify_api.playlist_create(playlist_name, False)
            spotify_id, name_created_with = playlist.id, playlist.name

        most_recent_sync = datetime.utcnow()
        unsynced_songs = [
            song
            for song in await self._youtube_api.get_video_infos_from_playlist(yt_playlist_id)
            if not last_synced or song["published_at"] >= last_synced
        ]
        if download:
            await self._handle_songs_to_download(unsynced_songs, name_created_with, sikulix_instructions)
        else:
            await self._add_songs_to_spotify_playlist(spotify_id, unsynced_songs)

        if self._storage.has_playlist_been_synced(yt_playlist_id):
            self._storage.update_last_synced(yt_playlist_id, most_recent_sync)
        else:
            self._storage.store_new_entry(yt_playlist_id, most_recent_sync, spotify_id, name_created_with)
        print(f"Finished syncing: {playlist_name}")

    @staticmethod
    def _add_songs_to_playlists_sikulix(instructions: SikuliInstructions):
        call_args = [
            "java", "-jar", f"{os.environ['HOME']}/sikulix/sikulixide-2.0.4.jar", "-r",
            f"{os.environ['HOME']}/programming/automation/ytToSpotify/src/local_files_automation.sikuli/", "--"
        ]
        for playlist, count in instructions:
            call_args.extend(["-e", f"{playlist},{count}"])
        subprocess.run(call_args)

    async def sync_playlists(self) -> None:
        sikulix_instructions: SikuliInstructions = []
        # TODO display progress bar for each individual playlist
        await asyncio.gather(
            *[
                self._sync_playlist(playlist_id, download, sikulix_instructions)
                for playlist_id, download in get_inputs().items()
            ]
        )
        if sikulix_instructions:
            proceed = input(
                "Would you like to automatially add the downloaded songs to their respective spotify playlists?\n"
                "If you wish to proceed, please disable any applications that can reverse the scroll direction\n"
                "for a mouse, not trackpad. (Y/n): "
            )
            if proceed.lower() == "y":
                self._add_songs_to_playlists_sikulix(sikulix_instructions)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", dest="verbose", action="store_true", help="Enables verbose mode for more detailed output"
    )
    parser.add_argument(
        "--max-parallel-downloads",
        dest="max_parallel_downloads",
        type=int,
        default=5,
        action="store",
        help=(
            "Maximum number videos that will be downloaded, if required, at once. "
            "Set this based on your network bandwight. Default is 5."
        ),
    )
    parser.add_argument(
        "--local-files-path",
        dest="local_files_path",
        default=None,
        action="store",
        help=(
            "Location of a spotify local files linked directory where downloaded songs will be saved to. Required "
            "if you have download enabled playlist setup for syncing."
        ),
    )
    args = parser.parse_args()
    async with get_spotify_api() as spotify_api, get_youtube_api() as youtube_api:
        psync = await PlaylistSyncher.get_instance(
            spotify_api,
            youtube_api,
            args.verbose,
            args.max_parallel_downloads,
            Path(args.local_files_path).expanduser(),
        )
        await psync.sync_playlists()

# TODO implement as cron job
# TODO use youtube thumbnail/playlist cover iamge for spotify cover image
if __name__ == '__main__':
    asyncio.run(main())
