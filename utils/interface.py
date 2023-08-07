import threading
import time
import asyncio
from enum import Enum
from queue import Queue

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

def safeformat(str, **kwargs):
    """
        Formats the passed string {str} using the given keyword arguments, while keeping missing replacements unformatted
    """
    
    class SafeDict(dict):
        def __missing__(self, key):
            return '{' + key + '}'
        
    replacements = SafeDict(**kwargs)
    
    return str.format_map(replacements)

DEFAULT_EVENT_FORMATS = {
        EventType.MESSAGE: "[{name}] {message}",
        EventType.START: "[{name}] Server started!",
        EventType.REGISTERED: "[{name}] Server registered with Playfab!",
        EventType.SHUTDOWN: "[{name}] Server shutdown!",
        EventType.CRASH: "[{name}] Server crashed!",
        EventType.PLAYER_JOIN: "[{name}] Player '{player}' joined the game",
        EventType.PLAYER_LEAVE: "[{name}] Player '{player}' left the game",
        EventType.COMMAND: "[{name}] Command executed: {command}"
    }

class NotificationHandler:
    """
        A class that can receive events and send them along as formatted messages to some endpoint
    """
    
    def __init__(self, name="Server", event_whitelist=set([e for e in EventType]), event_formats=DEFAULT_EVENT_FORMATS):
        self.name = name
        self.whitelist = event_whitelist
        self.formats = event_formats
    
    def send_event(self, event_type=EventType.MESSAGE, **params):
        """ Send event using the provided parameters """
        
        # Only send, if event is in whitelist
        if event_type in self.whitelist:
            # Add server name to parameters for formatting
            params["name"] = self.name
            message = safeformat(self.formats[event_type], **params)
            
            self._send_message(event_type, message)
    
    def _send_message(self, event_type, message):
        """
            Internal method to actually pass the message on.
            To be overwritten by subclasses.
        """
        
        print(message)

class QueuedNotificationHandler(NotificationHandler):
    """
        Notification handler that uses a thread and a queue to handle events asynchronously
    """
    
    class NotificationThread(threading.Thread):
        def __init__(self, callback, name="keyboard-input-thread"):
            self.callback = callback
            self.event_queue = Queue()
            self.wakeup_event = threading.Event()
            
            super(QueuedNotificationHandler.NotificationThread, self).__init__(name=name)
            self.daemon = True
            self.start()
        
        def add_event(self, event_type, message):
            """ Add an event to the internal queue """
            self.event_queue.put((event_type, message))
            self.wakeup_event.set()
        
        def run(self):
            while True:
                if not self.event_queue.empty():
                    # If the queue is not empty, there are events to handle
                    event = self.event_queue.get()
                    self.callback(*event)
                else:
                    # If queue is empty, sleep for 10s or until the wakeup_event is set
                    self.wakeup_event.wait(timeout=10)
                    self.wakeup_event.clear()
    
    def __init__(self, name="Server", event_whitelist=set([e for e in EventType]), event_formats=DEFAULT_EVENT_FORMATS):
        super().__init__(name, event_whitelist, event_formats)
        
        self.thread = QueuedNotificationHandler.NotificationThread(self._handle_message)
    
    def _send_message(self, event_type, message):
        self.thread.add_event(event_type, message)
    
    def _handle_message(self, event_type, message):
        """
            Method for handling events asynchronously.
            To be overritten by subclasses.
        """
        
        time.sleep(3)
        print(message)