import csv
import os
import pickle
from datetime_manager import datetime_to_timestamp_str, timestamp_str_to_datetime, generate_times_stamps, get_time_now

# TODO allow for multiple StorageManager objects to operate simultaneously
# storage:
# yt_playlist_id, spotify_playlist_id, last_synced_ts


class StorageManager:
    def __init__(self):
        self.store_path = './downloaded_songs_store'

    def read_storage(self):
        db = {}
        if os.path.getsize(self.store_path) > 0:
            with open(self.store_path, 'rb') as store:
                db = pickle.load(store)

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
        return yt_playlist_id in self.storage

    def store_new_entry(self, yt_playlist_id, spotify_pl_id):
        now = get_time_now()

        self.storage[yt_playlist_id] = {
            "spotify_playlist_id": spotify_pl_id,
            "last_synced_ts": now
        }

        print("storage after new entry:\n{}".format(self.storage))

    def get_last_synced_timestamp(self, yt_playlist_id):
        return self.storage[yt_playlist_id]['last_synced_ts']

    def get_spotify_playlist_id(self, yt_playlist_id):
        return self.storage[yt_playlist_id]['spotify_playlist_id']

    def update_last_synced(self, yt_playlist_id):
        self.storage[yt_playlist_id]['last_synced_ts'] = get_time_now()

        print("Storage after update of last synced timestamp for {0}:\n{1}".format(yt_playlist_id, self.storage))

    def get_db(self):
        db = {}
        if os.path.getsize(self.store_path) > 0:
            with open(self.store_path, 'rb') as store:
                db = pickle.load(store)

        return db

    def get_downloaded_songs(self, spotify_id):
        db = self.get_db()
        return db[spotify_id]

    def record_downloaded_song(self, spotify_id, video_id):
        with open('downloaded_songs_store', 'wb') as store:
            db = self.get_db()
            db[spotify_id].append(video_id) 
            pickle.dump(db, store)

    def record_downloaded_songs(self, spotify_id, video_ids):
        with open('downloaded_songs_store', 'wb') as store:
            db = self.get_db()

            if spotify_id not in db:
                db[spotify_id] = []

            for video_id in video_ids:
                db[spotify_id].append(video_id) 

            pickle.dump(db, store)

if __name__ == '__main__':
    storage = StorageManager()
    print(storage.get_last_synced_timestamp('PLucKeiEo64s_2ZXtW0Vv3kJ8rqFEvDJbf'))
    print(storage.get_spotify_playlist_id('PLucKeiEo64s_2ZXtW0Vv3kJ8rqFEvDJbf'))
