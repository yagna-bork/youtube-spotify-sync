# youtube-spotify-sync
Sync youtube playlists onto spotify. Download songs which have been marked as youtube exclusive to allow for spotify play.

# Instructions
1. Follow link for spotify authentication
1. Enter {code} in format redirect_url/?code={code}
1. Follow link for Google 0Auth authentication
1. DONE

# Features remaining
* Downloading songs from marked playlists
* Refactoring 
  * Refactor for readability
  * Improve runtime efficency of CreatePlaylist.add_songs_to_spotify_playlist list deletion
* Prevent duplicates of songs in CreatePlaylist.add_songs_to_spotify_playlist (spotify api?)
* Implement UI so getting spotify tokens is user friendly -> implement phone app frontend?
