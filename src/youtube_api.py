import typing as t
import google_auth_oauthlib.flow
import google.oauth2.credentials
import google.auth.transport.requests
import google.auth.exceptions
import json
from src.utils import CacheKeyringHandler
import aiogoogle
from aiogoogle.auth.creds import UserCreds
from contextlib import asynccontextmanager
from datetime import datetime
import re
from dateutil import parser


_google_keyring_handler = CacheKeyringHandler("yt2spotifysync", "google_secret_token_info")


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


class VideoInfo(t.TypedDict):
    """A subset of only the required data stored in snippet from Youtube API."""
    title: str
    published_at: datetime
    id: str
    url: str
    chapters: t.List[YoutubeChapter]


class YoutubeAPI:
    def __init__(self, agoogle: aiogoogle.Aiogoogle, youtube_v3: aiogoogle.resource.GoogleAPI):
        self._agoogle = agoogle
        self._youtube_v3 = youtube_v3

    @staticmethod
    def parse_chapter(line: str, format_to_use_idx: t.Optional[int] = None) -> t.Optional[t.Tuple[YoutubeChapter, int]]:
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
        valid_formats = valid_formats if format_to_use_idx is None else [valid_formats[format_to_use_idx]]
        for idx, format_ in enumerate(valid_formats):
            match = format_.match(line)
            if match:
                timestamp = match.group("ts1") or match.group("ts2") or match.group("ts3")
                title = match.group("title").strip()
                youtube_chapter = YoutubeChapter(YoutubeChapter.start_timestamp_to_seconds(timestamp), title)
                format_used_idx = format_to_use_idx or idx
                return youtube_chapter, format_used_idx

    @classmethod
    def parse_chapters_from_description(cls, description: str) -> t.List[YoutubeChapter]:
        chapters = []
        lines = description.split("\n")
        parsing_format_to_use_idx = None
        for line in lines:
            if result := cls.parse_chapter(line, parsing_format_to_use_idx):
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

    async def get_video_infos_from_playlist(self, playlist_id: str) -> t.List[VideoInfo]:
        res = await self._agoogle.as_user(
            self._youtube_v3.playlistItems.list(part="snippet,contentDetails", playlistId=playlist_id, maxResults=50),
            full_res=True
        )
        return [
            {
                "title": item["snippet"]["title"],
                "published_at": parser.isoparse(item["snippet"]["publishedAt"]),
                "id": item["contentDetails"]["videoId"],
                "url": f"https://www.youtube.com/watch?v={item['contentDetails']['videoId']}",
                "chapters": self.parse_chapters_from_description(item["snippet"]["description"]),
            }
            async for page in res
            for item in page["items"]
            if item["snippet"]["title"] not in ["Deleted video", "Private video"]
        ]

    async def get_playlist_name(self, playlist_id: str) -> t.Optional[str]:
        res = await self._agoogle.as_user(self._youtube_v3.playlists.list(part="snippet", id=playlist_id))
        return res["items"][0]["snippet"]["title"] if res["items"] else None


def _do_google_auth_flow(scopes: t.List[str]) -> google.oauth2.credentials.Credentials:
    # TODO switch to pkce
    secrets_file = "client_secret.json"
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(secrets_file, scopes)
    return flow.run_local_server()


def _get_google_apis_credentials(scopes: t.List[str]) -> google.oauth2.credentials.Credentials:
    user_info = None
    if user_info_json := _google_keyring_handler.get_cached_token():
        user_info = json.loads(user_info_json)
    if user_info:
        credentials = google.oauth2.credentials.Credentials.from_authorized_user_info(user_info)
        if credentials.valid:
            return credentials
        else:
            try:
                request = google.auth.transport.requests.Request()
                credentials.refresh(request)
            except google.auth.exceptions.RefreshError:
                print("Something went wrong with refreshing your google access token. Let's make a new one!")
            else:
                _google_keyring_handler.save_token_to_cache(credentials.to_json())
                return credentials

    credentials = _do_google_auth_flow(scopes)
    _google_keyring_handler.save_token_to_cache(credentials.to_json())
    return credentials


def get_user_creds(creds: google.oauth2.credentials.Credentials) -> UserCreds:
    return UserCreds(
        access_token=creds.token,
        refresh_token=creds.refresh_token,
        expires_at=creds.expiry.isoformat(),
        scopes=creds.scopes,
    )


@asynccontextmanager
async def get_youtube_api() -> YoutubeAPI:
    scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
    creds = _get_google_apis_credentials(scopes)
    user_creds = get_user_creds(creds)
    async with aiogoogle.Aiogoogle(user_creds=user_creds) as agoogle:
        youtube_v3 = await agoogle.discover("youtube", "v3")
        yield YoutubeAPI(agoogle, youtube_v3)
