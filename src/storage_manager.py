import os
import pickle
from datetime import datetime


# TODO allow for multiple StorageManager objects to operate simultaneously
class StorageManager:
    def __init__(self, db_file_path='songs_db'):
        """
        :param db_file_path:
        Postfix of path to database file. Prefix: /path/to/storage/manager/parent/
        E.g. db_file_path = "songs_db", path to storage manager parent = "/usr/yagnab/home/projects/", path used ->
        "/usr/yagnab/home/projects/songs_db"
        """

        self.db_file_path = os.path.dirname(__file__) + "/" + db_file_path

        # initialise empty db if file doesn't exist
        if not os.path.isfile(self.db_file_path) or os.path.getsize(self.db_file_path) == 0:
            empty_db = {
                "synced_playlists": {},
            }
            with open(self.db_file_path, 'w+b') as db:
                pickle.dump(empty_db, db)

    def get_database(self):
        with open(self.db_file_path, 'rb') as store:
            return pickle.load(store)

    def write_database(self, db):
        with open(self.db_file_path, 'wb') as db_file:
            pickle.dump(db, db_file)

    def has_playlist_been_synced(self, yt_playlist_id):
        db = self.get_database()
        return yt_playlist_id in db['synced_playlists']

    def store_new_entry(self, yt_playlist_id, spotify_playlist_id):
        db = self.get_database()
        now_ts = datetime.timestamp(datetime.utcnow())
        db['synced_playlists'][yt_playlist_id] = {
            "spotify_playlist_id": spotify_playlist_id,
            "last_synced_ts": now_ts,
        }

        self.write_database(db)

    def get_last_synced_timestamp(self, yt_playlist_id):
        db = self.get_database()
        return db['synced_playlists'][yt_playlist_id]['last_synced_ts']

    def get_spotify_playlist_id(self, yt_playlist_id):
        db = self.get_database()
        if yt_playlist_id not in db["synced_playlists"]:
            return None
        return db["synced_playlists"][yt_playlist_id]["spotify_playlist_id"]

    def update_last_synced(self, yt_playlist_id):
        db = self.get_database()
        now_ts = datetime.timestamp(datetime.utcnow())
        db["synced_playlists"][yt_playlist_id]["last_synced_ts"] = now_ts
        self.write_database(db)

    def seed_pickle_file(self):
        # schema for pickle database
        init_obj = {
            "synced_playlists": {
                "PLucKeiEo64s_2ZXtW0Vv3kJ8rqFEvDJbf": {
                    "spotify_playlist_id": "4dVm4zXMIU3HqjbVtRrtRV",
                    "last_synced_ts": 1599412611.302752,
                }, "LLEA6rXRPPbQur1xyOgurtQg": {
                    "spotify_playlist_id": "4EOYcqOkQMOPB8bWmzZc3U",
                    "last_synced_ts": 1599412631.782011,
                }, "PLucKeiEo64s9D4vtua7xIFZe-9YZdOmZP": {
                    "spotify_playlist_id": "5vAwYEmFbF2yRex2p7fwYB",
                    "last_synced_ts": 1594657869.692405,
                }, "PLucKeiEo64s9376jBeUh9ukrWv6L5k0Ox": {
                    "spotify_playlist_id": "2B46Xhd7rw6IRYWkcAGDO4",
                    "last_synced_ts": 1599412631.888807,
                }, "PLucKeiEo64s8tejNdkXCKo5xClilZ4Nni": {
                    "spotify_playlist_id": "4C5kAlMObPKLDRwsdkDg9y",
                    "last_synced_ts": 1594657869.171505,
                }
            },
            "slowed_songs": {},
        }
        self.write_database(init_obj)
        print("db after seeding: {}".format(self.get_database()))


if __name__ == '__main__':
    pass
