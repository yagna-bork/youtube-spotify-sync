import pytest
from datetime import datetime
import pickle
from ..storage_manager import StorageManager
import os
from os.path import dirname


@pytest.fixture
def seed_database():
    return {"synced_playlists": {
        "abc": {"spotify_playlist_id": "123", "last_synced_ts": 123456.123},
        "xyz": {"spotify_playlist_id": "789", "last_synced_ts": 654321.123}
    }}


@pytest.fixture
def db_get_paths_and_remove_file(request):
    db_path_here = 'db_instances/' + request.param  # TODO setup.py, relative file import
    TestStorageManager.delete_file_if_exists(db_path_here)
    return TestStorageManager.get_root_here_paths(db_path_here)


class TestStorageManager:
    @staticmethod
    def manual_write(db_data, db_path):
        db_path = dirname(__file__) + "/" + db_path
        with open(db_path, 'w+b') as db:
            pickle.dump(db_data, db)

    @staticmethod
    def manual_read(db_path):
        db_path = dirname(__file__) + "/" + db_path
        with open(db_path, 'rb') as db:
            return pickle.load(db)

    @staticmethod
    def delete_file_if_exists(path):
        if os.path.isfile(path):
            print("removing: {}".format(path))
            os.remove(path)

    @staticmethod
    def get_root_here_paths(here_path):
        root_path = "tests/" + here_path
        return root_path, here_path

    @pytest.mark.parametrize('db_get_paths_and_remove_file', ['test_get_database'], indirect=True)
    def test_get_database(self, seed_database, db_get_paths_and_remove_file):
        db_path_root, db_path_here = db_get_paths_and_remove_file
        self.manual_write(seed_database, db_path_here)

        db_manager = StorageManager(db_path_root)
        assert db_manager.get_database() == seed_database

    @pytest.mark.parametrize('db_get_paths_and_remove_file', ['test_write_database'], indirect=True)
    def test_write_database(self, seed_database, db_get_paths_and_remove_file):
        db_path_root, db_path_here = db_get_paths_and_remove_file
        db_manager = StorageManager(db_path_root)
        db_manager.write_database(seed_database)
        db_retrieved = self.manual_read(db_path_here)
        assert db_retrieved == seed_database

    @pytest.mark.parametrize('db_get_paths_and_remove_file', ['test_has_playlist_been_synced'], indirect=True)
    def test_has_playlist_been_synced(self, db_get_paths_and_remove_file):
        db_path_root, db_path_here = db_get_paths_and_remove_file
        db = StorageManager(db_path_root)
        db_data = {
            "synced_playlists": {
                "abc": {},
                "123": {},
            }
        }
        self.manual_write(db_data, db_path_here)

        assert db.has_playlist_been_synced('abc') is True
        assert db.has_playlist_been_synced('123') is True
        assert db.has_playlist_been_synced('invalid_pl_id') is False
        assert db.has_playlist_been_synced('another_invalid_pl_id') is False

    @pytest.mark.parametrize('db_get_paths_and_remove_file', ['test_store_new_entry'], indirect=True)
    def test_store_new_entry(self, db_get_paths_and_remove_file):
        db_path_root, db_path_here = db_get_paths_and_remove_file
        most_recent_sync, yt_id, spotify_id, spotify_name = datetime.utcnow(), "abc", "123", "abc"
        mock = {
            "synced_playlists": {
                yt_id: {'spotify_playlist_id': spotify_id, "last_synced_ts": None, "spotify_name": spotify_name}
            }
        }

        db_manager = StorageManager(db_path_root)
        db_manager.store_new_entry(yt_id, most_recent_sync, spotify_id, spotify_name)
        db = self.manual_read(db_path_here)
        stored_ts = db["synced_playlists"][yt_id]["last_synced_ts"]
        mock["synced_playlists"][yt_id]["last_synced_ts"] = stored_ts

        assert isinstance(stored_ts, float)
        assert db == mock

    @pytest.mark.parametrize('db_get_paths_and_remove_file', ['test_get_last_synced_timestamp'], indirect=True)
    def test_get_last_synced_timestamp(self, db_get_paths_and_remove_file, seed_database):
        db_path_root, db_path_here = db_get_paths_and_remove_file
        db_manager = StorageManager(db_path_root)
        self.manual_write(seed_database, db_path_here)
        retrieved_ts_abc = db_manager.get_last_synced_timestamp("abc")
        retrieved_ts_xyz = db_manager.get_last_synced_timestamp("xyz")

        assert isinstance(retrieved_ts_xyz, float) and isinstance(retrieved_ts_abc, float)
        assert retrieved_ts_abc == seed_database["synced_playlists"]["abc"]["last_synced_ts"]
        assert retrieved_ts_xyz == seed_database["synced_playlists"]["xyz"]["last_synced_ts"]

    @pytest.mark.parametrize('db_get_paths_and_remove_file', ['test_get_spotify_playlist_id'], indirect=True)
    def test_get_spotify_playlist_id(self, db_get_paths_and_remove_file):
        db_path_root, db_path_here = db_get_paths_and_remove_file
        db_data = {"synced_playlists": {"abc": {"spotify_playlist_id": "123"}}}
        self.manual_write(db_data, db_path_here)
        db_manager = StorageManager(db_path_root)

        assert db_manager.get_spotify_playlist_id("abc") == "123"

    # TODO apply mock here
    @pytest.mark.parametrize('db_get_paths_and_remove_file', ['test_get_spotify_playlist_id'], indirect=True)
    def test_update_last_synced(self, db_get_paths_and_remove_file, seed_database):
        db_path_root, db_path_here = db_get_paths_and_remove_file
        self.manual_write(seed_database, db_path_here)
        db_manager = StorageManager(db_path_root)
        db_manager.update_last_synced("abc", datetime.utcnow())
        db = self.manual_read(db_path_here)
        assert isinstance(db["synced_playlists"]["abc"]["last_synced_ts"], float)
