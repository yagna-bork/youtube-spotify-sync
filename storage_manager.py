import csv
from datetime import datetime
import time

# TODO allow for multiple StorageManager objects to operate simultaneously
# storage:
# yt_playlist_id, spotify_playlist_id, last_synced_ts


class StorageManager:
    def __init__(self):
        self.storage = self.read_storage()

        # TODO remove need for this
        self.destroyed = False

    @staticmethod
    def read_storage():
        storage_dict = {}

        with open('storage.csv', 'r') as file:
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
        if not self.destroyed:
            print("about to write to output.csv:\n{0}".format(self.storage))

            with open('storage.csv', 'w') as file:
                writer = csv.writer(file, delimiter=',')

                for yt_playlist_id, values in self.storage.items():
                    spotify_playlist_id = values['spotify_playlist_id']

                    # convert datetime to timestamp before storing
                    timestamp = datetime.timestamp(values['last_synced_ts'])

                    writer.writerow([yt_playlist_id, spotify_playlist_id, timestamp])

            self.destroyed = True

    def has_playlist_been_synced(self, yt_playlist_id):
        return yt_playlist_id in self.storage

    def store_new_entry(self, yt_playlist_id, spotify_pl_id):
        now = datetime.now()

        self.storage[yt_playlist_id] = {
            "spotify_playlist_id": spotify_pl_id,
            "last_synced_ts": now
        }

        print("storage after new entry:\n{}".format(self.storage))

    def get_last_synced_timestamp(self, yt_playlist_id):
        return self.storage[yt_playlist_id]['last_synced_ts']

    def get_spotify_playlist_id(self, yt_playlist_id):
        return self.storage[yt_playlist_id]['spotify_playlist_id']

def generate_times_stamps():
    for i in range(3):
        now = datetime.now()
        now_ts = datetime.timestamp(now)
        print(now_ts)
        time.sleep(3)

if __name__ == '__main__':
    storage = StorageManager()
    print(storage.get_last_synced_timestamp('PLucKeiEo64s_2ZXtW0Vv3kJ8rqFEvDJbf'))
    print(storage.get_spotify_playlist_id('PLucKeiEo64s_2ZXtW0Vv3kJ8rqFEvDJbf'))
