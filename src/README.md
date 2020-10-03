# youtube-spotify-sync
Sync youtube playlists onto spotify. Download songs which have been marked as youtube exclusive to allow for spotify play.

## Instructions
1. Create input.csv format: [Youtube playlist id,Songs need to be downloaded (true/false)]
1. Create empty storage.csv file
1. Follow link for spotify authentication
1. Enter {code} in format redirect_url/?code={code}
1. Execute curl command printed in seperate terminal tab or window and paste in the recieved code
1. Follow link for Google 0Auth authentication
1. DONE

## Features remaining
* Downloading songs from marked playlists
* Refactoring 
  * Refactor for readability
  * Improve runtime efficency of CreatePlaylist.add_songs_to_spotify_playlist list deletion
* Prevent duplicates of songs in CreatePlaylist.add_songs_to_spotify_playlist (spotify api?)
* storage.csv created by itself & terminal prompt to create input.csv?
* Flesh out instructions OR
  * Implement UI so getting spotify tokens is user friendly -> implement phone app frontend?

