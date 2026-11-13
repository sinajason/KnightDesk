"""Background bridge to Windows' currently selected media session."""
import asyncio
from queue import Empty, SimpleQueue
from threading import Event, Thread


class MediaSession:
    def __init__(self, publish):
        self.publish = publish
        self.active = Event()
        self.wake = Event()
        self.commands = SimpleQueue()
        self.worker = None

    def set_active(self, active):
        if active:
            self.active.set()
            if self.worker is None:
                self.worker = Thread(target=self.run, daemon=True)
                self.worker.start()
        else:
            self.active.clear()
        self.wake.set()

    def command(self, action):
        if self.active.is_set() and self.worker and self.worker.is_alive():
            self.commands.put(action)
            self.wake.set()

    def run(self):
        try:
            from winrt.runtime import ApartmentType, init_apartment, uninit_apartment
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
            from winrt.windows.storage.streams import DataReader
            init_apartment(ApartmentType.MULTI_THREADED)
        except (ImportError, OSError, RuntimeError):
            self.publish({"unavailable": True})
            return
        try:
            asyncio.run(self.poll(Manager, DataReader))
        finally:
            uninit_apartment()

    async def poll(self, manager_type, reader_type):
        manager = None
        last_track, cover = None, b""
        last_report = None
        while True:
            self.wake.clear()
            if not self.active.is_set():
                await asyncio.to_thread(self.wake.wait)
                continue
            interval = 2
            try:
                if manager is None:
                    manager = await asyncio.wait_for(manager_type.request_async(), 5)
                session = manager.get_current_session()
                while True:
                    try:
                        action = self.commands.get_nowait()
                    except Empty:
                        break
                    if session:
                        call = {
                            "previous": session.try_skip_previous_async,
                            "toggle": session.try_toggle_play_pause_async,
                            "next": session.try_skip_next_async,
                        }[action]
                        await asyncio.wait_for(call(), 3)
                report = {}
                if session:
                    track = await asyncio.wait_for(session.try_get_media_properties_async(), 4)
                    if track:
                        identity = session.source_app_user_model_id, track.title, track.artist, track.album_title
                        if identity != last_track:
                            cover = await self.artwork(track.thumbnail, reader_type)
                            last_track = identity
                        playback = session.get_playback_info()
                        report = {"title": track.title, "artist": track.artist, "cover": cover,
                                  "playing": bool(playback and playback.playback_status.name == "PLAYING")}
            except (OSError, RuntimeError, TypeError, asyncio.TimeoutError):
                manager = None
                report = {"unavailable": True}
                interval = 6
            if report != last_report:
                self.publish(report)
                last_report = report
            await asyncio.to_thread(self.wake.wait, interval)

    @staticmethod
    async def artwork(thumbnail, reader_type):
        if not thumbnail:
            return b""
        try:
            stream = await asyncio.wait_for(thumbnail.open_read_async(), 3)
            try:
                size = stream.size
                if not 0 < size <= 4 * 1024 * 1024:
                    return b""
                with stream.get_input_stream_at(0) as source, reader_type(source) as reader:
                    count = await asyncio.wait_for(reader.load_async(size), 3)
                    data = bytearray(count)
                    reader.read_bytes(data)
                    return bytes(data)
            finally:
                stream.close()
        except (OSError, RuntimeError, TypeError, ValueError, asyncio.TimeoutError):
            return b""
