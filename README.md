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
* investigate disappearing downloaded songs bug mobile
* investigate forcing download of new songs on mobile
* Use youtube thumbnail as cover art in id3 tag
* Investigate downloaded songs w/ chapter in wrong order after async
* Implement as Cron job, UI dashboard should configure how often synced, when is next sync etc...
* Refactoring 
  * Stop using youtube title parser and regex description/look into youtube dl fix
  * Prevent "WARNING: Requested formats are incompatible for merge and will be merged into mkv." and following slow mp4 download
* web interface prompt to create input.csv?
* slow down any song from spotify
* upload slowed reverb generated songs directly to youtube -> increase the circulation of slowed songs

## Django todo list
* 0Auth web interface/login
  * Simple button called sync which runs script
* Add playlists web interface
* Display of instruction logs
