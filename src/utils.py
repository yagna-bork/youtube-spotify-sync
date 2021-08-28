from spotipy.cache_handler import CacheHandler
import keyring
from keyring.errors import InitError, PasswordSetError
import asyncio
import typing as t


class CacheKeyringHandler(CacheHandler):
    """Handles reading and writing authorization tokens stored in the system keyring."""

    def __init__(self, keyring_service_id, key):
        """
        Parameters:
             * keyring_service_id: The service id that will be associated with your apps keyring storage
             * key: A key unique to keyring_service_id under which the token will be stored
        """
        self.keyring_service_id = keyring_service_id
        self.key = key

    def get_cached_token(self) -> t.Optional[str]:
        try:
            return keyring.get_password(self.keyring_service_id, self.key)
        except InitError:
            print("Couldn't initalise the %s keyring service while trying to read", self.keyring_service_id)
        return None

    def save_token_to_cache(self, token_info: str) -> None:
        try:
            keyring.set_password(self.keyring_service_id, self.key, token_info)
        except PasswordSetError:
            print("Couldn't write token to the %s keyring service", self.keyring_service_id)
        except InitError:
            print("Couldn't initalise the %s keyring service while trying to write", self.keyring_service_id)


async def run_command_async(cmd: str) -> bool:
    proc = await asyncio.create_subprocess_shell(cmd)
    await proc.communicate()
    return proc.returncode == 0
