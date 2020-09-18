import csv
import os
import pickle
from datetime_manager import datetime_to_timestamp, timestamp_str_to_datetime, generate_times_stamps, get_time_now


# TODO allow for multiple StorageManager objects to operate simultaneously
# storage:
# yt_playlist_id, spotify_playlist_id, last_synced_ts


class StorageManager:
    def __init__(self, db_file_path='songs_db'):
        self.db_file_path = db_file_path

    def get_database(self):
        if os.path.getsize(self.db_file_path) > 0:
            with open(self.db_file_path, 'rb') as store:
                db = pickle.load(store)
        else:
            db = {}
            with open(self.db_file_path, 'w+') as store:
                pickle.dump(db, store)
        return db

    # must call at end
    def write_storage(self):
        if not self.destroyed:
            print("about to write to output.csv:\n{0}".format(self.storage))

            with open('storage.csv', 'w') as file:
                writer = csv.writer(file, delimiter=',')

                for yt_playlist_id, values in self.storage.items():
                    spotify_playlist_id = values['spotify_playlist_id']

                    timestamp = datetime_to_timestamp_str(values['last_synced_ts'])

                    writer.writerow([yt_playlist_id, spotify_playlist_id, timestamp])

            self.destroyed = True

    def has_playlist_been_synced(self, yt_playlist_id):
        db = self.get_database()
        return yt_playlist_id in db['synced_playlists']

    def store_new_entry(self, yt_playlist_id, spotify_playlist_id):
        db = self.get_database()
        now = get_time_now()
        db['synced_playlists'][yt_playlist_id] = {
            "spotify_playlist_id": spotify_playlist_id,
            "last_synced_ts": now,
        }

        with open(self.db_file_path, 'wb') as db_file:
            pickle.dump(db, db_file)

    def get_last_synced_timestamp(self, yt_playlist_id):
        db = self.get_database()
        return db['synced_playlists'][yt_playlist_id]['last_synced']

    def get_spotify_playlist_id(self, yt_playlist_id):
        return self.storage[yt_playlist_id]['spotify_playlist_id']

    def update_last_synced(self, yt_playlist_id):
        self.storage[yt_playlist_id]['last_synced_ts'] = get_time_now()

        print("Storage after update of last synced timestamp for {0}:\n{1}".format(yt_playlist_id, self.storage))

    def get_downloaded_songs(self, spotify_id):
        db = self.get_database()
        return db[spotify_id]

    def record_downloaded_song(self, spotify_id, video_id):
        with open('downloaded_songs_store', 'wb') as store:
            db = self.get_database()
            db[spotify_id].append(video_id)
            pickle.dump(db, store)

    def record_downloaded_songs(self, spotify_id, video_ids):
        with open('downloaded_songs_store', 'wb') as store:
            db = self.get_database()

            if spotify_id not in db:
                db[spotify_id] = []

            for video_id in video_ids:
                db[spotify_id].append(video_id)

            pickle.dump(db, store)

    def seed_pickle_file(self):
        file = self.db_file_path
        # schema for pickle database
        init_obj = {
            "synced_playlists": {
                "PLucKeiEo64s_2ZXtW0Vv3kJ8rqFEvDJbf": {
                    "spotify_playlist_id": "4dVm4zXMIU3HqjbVtRrtRV",
                    "last_synced": 1599412611.302752,
                }, "LLEA6rXRPPbQur1xyOgurtQg": {
                    "spotify_playlist_id": "4EOYcqOkQMOPB8bWmzZc3U",
                    "last_synced": 1599412631.782011,
                }, "PLucKeiEo64s9D4vtua7xIFZe-9YZdOmZP": {
                    "spotify_playlist_id": "5vAwYEmFbF2yRex2p7fwYB",
                    "last_synced": 1594657869.692405,
                }, "PLucKeiEo64s9376jBeUh9ukrWv6L5k0Ox": {
                    "spotify_playlist_id": "2B46Xhd7rw6IRYWkcAGDO4",
                    "last_synced": 1599412631.888807,
                }, "PLucKeiEo64s8tejNdkXCKo5xClilZ4Nni": {
                    "spotify_playlist_id": "4C5kAlMObPKLDRwsdkDg9y",
                    "last_synced": 1594657869.171505,
                }
            },
            "slowed_songs": {},
        }

        with open(file, 'wb') as store:
            pickle.dump(init_obj, store)

        print("db after seeding: {}".format(self.get_database()))


if __name__ == '__main__':
    storage = StorageManager()
    # TODO test in CreatePlaylist.py
