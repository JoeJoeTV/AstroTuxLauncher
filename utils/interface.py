import threading
import time
import asyncio
from enum import Enum

class KeyboardThread(threading.Thread):
    """
        Class for asynchronously getting keyboard input from the user
    """

    def __init__(self, callback=None, active=False, name="keyboard-input-thread"):
        self.callback = callback
        self.active = active
        super(KeyboardThread, self).__init__(name=name)
        self.daemon = True
        self.start()
    
    def run(self):
        while True:
            if active:
                self.callback(input())
            else:
                time.sleep(0.1)

class EventType(Enum):
    MESSAGE = "message"
    START = "start"
    REGISTERED = "registered"
    SHUTDOWN = "shutdown"
    CRASH = "crash"
    PLAYER_JOIN = "player_join"
    PLAYER_LEAVE = "player_leave"
    COMMAND = "command"

def safeformat(str, **kwargs):
    
    class SafeDict(dict):
        def __missing__(self, key):
            return '{' + key + '}'
        
    replacements = SafeDict(**kwargs)
    
    return str.format_map(replacements)

class NotificationHandler():
    """
        A class representing something which can handle notifications
    """
    
    DEFAULT_FORMATS = {
        EventType.MESSAGE: "[{server_name}] {message}",
        EventType.START: "[{server_name}] Server started!",
        EventType.REGISTERED: "[{server_name}] Server registered with Playfab!",
        EventType.SHUTDOWN: "[{server_name}] Server shutdown!",
        EventType.CRASH: "[{server_name}] Server crashed!",
        EventType.PLAYER_JOIN: "[{server_name}] Player '{player}' joined the game",
        EventType.PLAYER_LEAVE: "[{server_name}] Player '{player}' left the game",
        EventType.COMMAND: "[{server_name}] Command executed: {command}"
    }
    
    def __init__(self, server_name="Gameserver", event_whitelist=set([e for e in EventType]), event_formats=DEFAULT_FORMATS):
        self.server_name = server_name
        self.whitelist = event_whitelist
        self.formats = event_formats
    
    def send_event(self, event_type=EventType.MESSAGE, **params):
        if event_type in self.whitelist:
            # Add server name to parameters for formatting
            params["server_name"] = self.server_name
            message = safeformat(self.formats[event_type], **params)
            
            self._send_message(event_type, message)
    
    def _send_message(self, event_type, message):
        print(message)