import pytest
import typing as t
from ..CreatePlaylist import CreatePlaylist, YoutubeChapter


# regular CreatePlaylist has __init__ that requires 0Auth for spotify/yt tokens which we don't for testing
class CreatePlaylistEmptyInit(CreatePlaylist):
    def __init__(self):
        pass


@pytest.mark.parametrize(
    "description_file,expected_chapters",
    [
        (
            "description",
            [
                YoutubeChapter(0, "1. Memento Mori Intro (I Love You)"),
                YoutubeChapter(65, "2. One Of Those Nights (Demo)"),
                YoutubeChapter(125, "3. Angel Face"),
            ]
        ),
        (
            "description2",
            [
                YoutubeChapter(0, "fantompower - blankets"),
                YoutubeChapter(172, "mell-ø - deja vu"),
                YoutubeChapter(289, "High Noon Rush - Kane"),
                YoutubeChapter(441, "lilac - last train home together"),
            ]
        ),
        (
            "description3",
            [
                YoutubeChapter(0, "Neopolitin - Guustavv"),
                YoutubeChapter(143, "Seaside Swing - Guustavv"),
                YoutubeChapter(264, "Solarity - Guustavv"),
                YoutubeChapter(396, "Air Conditioning - Guustavv"),
            ]
        ),
        (
            "description4",
            [
                YoutubeChapter(0, "Pure Imagination- Future James"),
                YoutubeChapter(266, "Blue Boi - Lakey Inspired"),
                YoutubeChapter(470, "The Girl Next Door - Tomppabeats"),
                YoutubeChapter(43820, "Test long timestamp"),
            ]
        ),
        (
            "repeated_seperators_description",
            [
                YoutubeChapter(0, "SEE YOU IN UTOPIA [Prod. By Forgotten]"),
                YoutubeChapter(74, "FRANCHISE 2.0 [Prod. By Forgotten]"),
                YoutubeChapter(292, "ZOOM [Prod. By Forgotten]"),
                YoutubeChapter(463, "LOADED [Prod. By Forgotten]"),
            ]
        ),
        ("invalid_first_timestamp_description", []),
        ("no_timestamps_description", []),
        ("empty_description", []),
        (
            "inconsistent_timestamp_formats",
            [
                YoutubeChapter(0, "First format 1"),
                YoutubeChapter(60, "First format 2"),
                YoutubeChapter(300, "First format 3"),
            ]
        ),
    ]
)
def test_parse_chapters_from_description(description_file: str, expected_chapters: t.Tuple[str, str]) -> None:
    with open(f"tests/data/{description_file}", "r") as file:  # TODO setup.py, relative file import
        description = file.read()
    cp = CreatePlaylistEmptyInit()
    parsed_chapters = cp.parse_chapters_from_description(description)

    assert parsed_chapters == expected_chapters
