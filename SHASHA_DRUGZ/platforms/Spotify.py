import re
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from youtubesearchpython.__future__ import VideosSearch
import config

class SpotifyAPI:
    def __init__(self):
        self.regex = r"^(https:\/\/open.spotify.com\/)(.*)$"
        self.client_id = config.SPOTIFY_CLIENT_ID
        self.client_secret = config.SPOTIFY_CLIENT_SECRET
        self._yt_cache = {}  # cache YouTube results by track name

        if config.SPOTIFY_CLIENT_ID and config.SPOTIFY_CLIENT_SECRET:
            self.client_credentials_manager = SpotifyClientCredentials(
                self.client_id, self.client_secret
            )
            self.spotify = spotipy.Spotify(
                client_credentials_manager=self.client_credentials_manager
            )
        else:
            self.spotify = None

    async def valid(self, link: str):
        return bool(re.search(self.regex, link))

    # ✅ Only 1 Spotify API call — returns list of track name strings
    # Does NOT search YouTube at all
    async def playlist(self, url):
        playlist = self.spotify.playlist(url)
        playlist_id = playlist["id"]
        results = []

        # Handle pagination for 100+ song playlists
        tracks = playlist["tracks"]
        while tracks:
            for item in tracks["items"]:
                if not item or not item.get("track"):
                    continue
                music_track = item["track"]
                info = music_track["name"]
                for artist in music_track["artists"]:
                    fetched = f' {artist["name"]}'
                    if "Various Artists" not in fetched:
                        info += fetched
                results.append(info)

            # Fetch next page if exists
            if tracks["next"]:
                tracks = self.spotify.next(tracks)
            else:
                break

        return results, playlist_id

    # ✅ Call this separately, one song at a time, right before playing
    async def fetch_youtube(self, track_name: str):
        # Return cached result if already searched before
        if track_name in self._yt_cache:
            return self._yt_cache[track_name]

        results = VideosSearch(track_name, limit=1)
        for result in (await results.next())["result"]:
            track_details = {
                "title": result["title"],
                "link": result["link"],
                "vidid": result["id"],
                "duration_min": result["duration"],
                "thumb": result["thumbnails"][0]["url"].split("?")[0],
            }
            self._yt_cache[track_name] = (track_details, result["id"])
            return track_details, result["id"]

    async def track(self, link: str):
        track = self.spotify.track(link)
        info = track["name"]
        for artist in track["artists"]:
            fetched = f' {artist["name"]}'
            if "Various Artists" not in fetched:
                info += fetched
        return await self.fetch_youtube(info)

    async def album(self, url):
        album = self.spotify.album(url)
        album_id = album["id"]
        results = []
        for item in album["tracks"]["items"]:
            info = item["name"]
            for artist in item["artists"]:
                fetched = f' {artist["name"]}'
                if "Various Artists" not in fetched:
                    info += fetched
            results.append(info)
        return results, album_id

    async def artist(self, url):
        artistinfo = self.spotify.artist(url)
        artist_id = artistinfo["id"]
        results = []
        artisttoptracks = self.spotify.artist_top_tracks(url)
        for item in artisttoptracks["tracks"]:
            info = item["name"]
            for artist in item["artists"]:
                fetched = f' {artist["name"]}'
                if "Various Artists" not in fetched:
                    info += fetched
            results.append(info)
        return results, artist_id
