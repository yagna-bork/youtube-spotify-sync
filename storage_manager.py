import csv
from datetime import datetime
import time

# TODO allow for multiple StorageManager objects to operate simultaneously
# storage:
# yt_playlist_id, spotify_playlist_id, last_synced_ts


class StorageManager:
    def __init__(self):
        self.storage = self.read_storage()

    @staticmethod
    def read_storage():
        storage_dict = {}

        with open('storage.csv') as file:
            reader = csv.reader(file)

            for idx, row in enumerate(reader):
                # store row as entry into storage dict
                storage_dict[row[0]] = {
                    "spotify_playlist_id": row[1],
                    "last_synced_ts": datetime.fromtimestamp(float(row[2]))
                }

        return storage_dict

    # must call at end
    def write_storage(self):
        print("Implement writing to storage")

    def has_playlist_been_synced(self, yt_playlist_id):
        return yt_playlist_id in self.storage


def generate_times_stamps():
    for i in range(3):
        now = datetime.now()
        now_ts = datetime.timestamp(now)
        print(now_ts)
        time.sleep(3)

if __name__ == '__main__':
    storage = StorageManager()

