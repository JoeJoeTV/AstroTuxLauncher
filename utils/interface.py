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

class NotificationManager:
    """ Class that keeps multiple Notification Handlers and broadcasts messages to all of them """
    
    def __init__(self):
        self.handlers = []
    
    def add_handler(self, handler):
        """ Add notification handler to manager """
        self.handlers.append(handler)
    
    def clear(self):
        self.handlers.clear()
    
    def send_event(self, event_type=EventType.MESSAGE, **params):
        """ Send event to all registered notification handlers """
        for handler in self.handlers:
            handler.send_event(event_type, **params)


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
    """
        Formats the passed string {str} using the given keyword arguments, while keeping missing replacements unformatted
    """
    
    class SafeDict(dict):
        def __missing__(self, key):
            return '{' + key + '}'
        
    replacements = SafeDict(**kwargs)
    
    return str.format_map(replacements)

class NotificationHandler():
    """
        A class that can receive events and send them along as formatted messages to some endpoint
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
        """ Send event using the provided parameters """
        if event_type in self.whitelist:
            # Add server name to parameters for formatting
            params["server_name"] = self.server_name
            message = safeformat(self.formats[event_type], **params)
            
            self._send_message(event_type, message)
    
    def _send_message(self, event_type, message):
        print(message)