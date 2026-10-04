import aiohttp
from datetime import datetime
from typing import Optional, Dict, Any

class RobloxAPI:
    """Helper client for interacting with official public Roblox Web APIs."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Look up a Roblox user by their username.
        Returns a dict with 'id', 'name', 'displayName' or None if not found.
        """
        session = await self.get_session()
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {
            "usernames": [username],
            "excludeBannedUsers": False
        }

        try:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user_list = data.get("data", [])
                    if user_list:
                        return user_list[0]
                return None
        except Exception as e:
            print(f"[RobloxAPI] Error searching username {username}: {e}")
            return None

    async def get_user_details(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch full details for a Roblox user ID, including bio description and created date.
        """
        session = await self.get_session()
        url = f"https://users.roblox.com/v1/users/{user_id}"

        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            print(f"[RobloxAPI] Error fetching details for user {user_id}: {e}")
            return None

    async def get_user_headshot(self, user_id: int) -> Optional[str]:
        """
        Retrieve user avatar headshot thumbnail URL.
        """
        session = await self.get_session()
        url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png&isCircular=false"

        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    thumbnails = data.get("data", [])
                    if thumbnails and thumbnails[0].get("state") == "Completed":
                        return thumbnails[0].get("imageUrl")
                return None
        except Exception as e:
            print(f"[RobloxAPI] Error fetching headshot for user {user_id}: {e}")
            return None

    @staticmethod
    def parse_creation_date(iso_str: str) -> Optional[datetime]:
        """Parses Roblox ISO date string into a Python datetime object."""
        try:
            # Handle formats like '2006-02-27T21:06:40.3Z' or '2020-01-01T00:00:00.000Z'
            cleaned = iso_str.rstrip("Z")
            if "." in cleaned:
                # Truncate fractional seconds to 6 digits for standard strptime/fromisoformat
                base, frac = cleaned.split(".", 1)
                frac = frac[:6]
                cleaned = f"{base}.{frac}"
            return datetime.fromisoformat(cleaned)
        except Exception:
            return None
