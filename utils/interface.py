import threading
import time
import asyncio
from enum import Enum
from queue import Queue, Empty
import logging
import colorlog
import sys
import os
from datetime import datetime, timezone
import argparse
import re
import subprocess
from alive_progress.animations.spinners import frame_spinner_factory
from utils.misc import LAUNCHER_VERSION
import utils.net as net
import json
from requests.utils import requote_uri
import urllib.parse as urlparse
from utils.termutils import ANSI

# Hack to detect wether UTF-8 symbols in the progress bar will cause problems
def _check_fancy_symbol_support():
    try:
        print('\u28f7', end="", flush=True)
        ANSI.clear_line()
        print("\r", end="", flush=True)
        return True
    except UnicodeEncodeError:
        return False

# Print character that causes problems and if an error occurs, we turn off fancy symbol support for progress bars
ENABLE_FANCY_PROGRESS_SYMBOLS = _check_fancy_symbol_support()

if ENABLE_FANCY_PROGRESS_SYMBOLS:
    AP_SPINNER = frame_spinner_factory("⣷⣯⣟⡿⢿⣻⣽⣾")
    AP_BAR = "smooth"
else:
    AP_SPINNER = "classic"
    AP_BAR = "classic"

LOGGER = logging.getLogger("Interface")

#
#   User Input
#

class KeyboardThread(threading.Thread):
    """
        Class for asynchronously getting keyboard input from the user
    """

    def __init__(self, callback=None, active=False, name="keyboard-input-thread"):
        self.callback = callback
        self.active = active
        
        super(KeyboardThread, self).__init__(name=name)
        
        self.daemon = True
        self.logger = logging.getLogger(name)
    
    def set_active(self, active=True):
        try:
            self.active = active
            
            self.logger.debug(f"Set input thread active: {str(self.active)}")
        except Exception as e:
            self.logger.error(f"Error in input thread set_active: {str(e)}")
    
    def run(self):
        try:
            while True:
                input_string = input()
                
                self.logger.debug(f"Got input: {input_string}")
                
                # Only process input, if active, else, ignore it
                if self.active:
                    self.callback(input_string)
        except Exception as e:
            self.logger.error(f"Error in input thread run: {str(e)}")


#
#   Process Output
#

class ProcessOutputThread(threading.Thread):
    """
        Class that reads the output of a process in another thread and adds each line to the given queue
    """

    def __init__(self, out, queue, name="process-output-thread"):
        """
            Create a new process output thread
            
            Arguments:
                - out: The stdout or stderr of a process
                - queue: A Queue to put the lines in
        """
        self.out = out
        self.queue = queue
        
        super(ProcessOutputThread, self).__init__(name=name)
        
        self.daemon = True
        self._stop_event = threading.Event()
        
        self.logger = logging.getLogger(name)
    
    def stop(self):
        self._stop_event.set()
    
    def stopped(self):
        return self._stop_event.is_set()
    
    def run(self):
        """ Reads lines from process and adds them to queue """
        try:
            for line in iter(self.out.readline, b''):
                
                # If stop event is set, stop reading and finish thread
                if self._stop_event.is_set():
                    break
                
                self.queue.put(line)
            
            self.out.close()
        except Exception as e:
            self.logger.error(f"Error in process output thread: {str(e)}")

#
#   Console Command Parsing
#

class IllegalArgumentError(Exception):
    """ Is raised by custom ArgumentParser subclass, when an error occurs that would normally exit the program """
    
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message
        
class ArgumentParser(argparse.ArgumentParser):
    """ Subclass overriding the error method to stop the ArgumentParse from exiting the whole program, if a parsing error occurs """
    
    def error(self, message):
        """error(message: string)

        Prints a usage message incorporating the message to stderr and
        exits.

        If you override this in a subclass, it should not return -- it
        should either exit or raise an exception.
        """
        if self.exit_on_error:
            self.print_usage(_sys.stderr)
            args = {'prog': self.prog, 'message': message}
            self.exit(2, _('%(prog)s: error: %(message)s\n') % args)
        else:
            raise IllegalArgumentError(message)

class EnumStoreAction(argparse.Action):
    """
        Action class to use for argparse add_argument method to allow enum values to be saved directly
    """
    
    def __init__(self, option_strings, dest, nargs=None, const=None, default=None, type=None, choices=None, required=False, help=None, metavar=None):
        if type is None:
            raise ValueError("type has to be assigned an enum")
        
        if not issubclass(type, Enum):
            raise TypeError("type has to be of type or subclass of Enum")
        
        self._enum = type
        self._enum_choices = [e.value for e in self._enum]
        
        super().__init__(option_strings=option_strings, dest=dest, nargs=nargs, const=const, default=default, type=None, choices=self._enum_choices, required=required, help=help, metavar=metavar)
    
    def __call__(self, parser, namespace, value, option_string=None):
        setattr(namespace, self.dest, self._enum(value))

class SubParserEnumStoreAction(argparse._SubParsersAction):
    """
        Action class to use for argparse add_subparsers method to get enum values from subcommand names
    """
    
    def __init__(self, option_strings, prog, parser_class, dest=argparse.SUPPRESS, required=False, help=None, metavar=None, type=None):
        if type is None:
            raise ValueError("type has to be assigned an enum")
        
        if not issubclass(type, Enum):
            raise TypeError("type has to be of type or subclass of Enum")

        self._enum = type
        self._enum_choices = [e.value for e in self._enum]
        
        super().__init__(option_strings=option_strings, prog=prog, parser_class=parser_class, dest=dest, required=required, help=help, metavar=metavar)
    
    def add_parser(self, name, **kwargs):
        # Support specifying enum members as names
        if isinstance(name, Enum):
            name = name.value
        
        if not (name in self._enum_choices):
            raise ValueError("name has to be a member of given enum")
        
        return super().add_parser(name, **kwargs)
    
    def __call__(self, parser, namespace, values, option_string=None):
        # Get parser_name first, before calling super method
        parser_name = values[0]
        
        # Call method from superclass first, such that the attribute is set
        super().__call__(parser, namespace, values, option_string)
        
        # If requested, get attribute set by super method and convert it to an enum
        if self.dest is not argparse.SUPPRESS:
            val = getattr(namespace, self.dest, None)
            
            try:
                val = self._enum(val)
            except ValueError:
                args = {'value': val,
                        'choices': ', '.join(self._enum_choices)}
                msg = _('unknown enum value %(parser_name)r (choices: %(choices)s)') % args
                raise argparse.ArgumentError(self, msg)
            
            # Update value in namespace with converted enum
            setattr(namespace, self.dest, val)

class ConsoleParser:
    """ Parser for console commands """
    
    class Command(Enum):
        HELP = "help"
        SHUTDOWN = "shutdown"
        RESTART = "restart"
        INFO = "info"
        KICK = "kick"
        WHITELIST = "whitelist"
        LIST = "list"
        SAVEGAME = "savegame"
        PLAYER = "player"
    
    class WhitelistSubcommand(Enum):
        ENABLE = "enable"
        DISABLE = "disable"
        STATUS = "status"
    
    class ListCategory(Enum):
        ALL = "all"
        WHITELISTED = "whitelisted"
        BLACKLISTED = "blacklisted"
        UNLISTED = "unlisted"
        ADMIN = "admin"
        OWNER = "owner"
    
    class SaveGameSubcommand(Enum):
        LOAD = "load"
        SAVE = "save"
        NEW = "new"
        LIST = "list"
    
    class PlayerSubcommand(Enum):
        SET = "set"
        GET = "get"
        
    class PlayerCategory(Enum):
        UNLISTED = "unlisted"
        BLACKLISTED = "blacklisted"
        WHITELISTED = "whitelisted"
        ADMIN = "admin"
    
    def __init__(self):
        self.parser = ArgumentParser(prog="", add_help=False, exit_on_error=False)
        
        subparser_section = self.parser.add_subparsers(parser_class=ArgumentParser, title="Command", description=None, dest="cmd", type=ConsoleParser.Command, action=SubParserEnumStoreAction, required=True)
        
        self.subparsers = {}
        
        # Add subparsers and arguments for commands
        
        ## 'help' command
        self.subparsers["help"] = subparser_section.add_parser(ConsoleParser.Command.HELP, help="Prints this help message and help messages for commands and subcommands", description="Prints this help message and help messages for commands and subcommands", add_help=False, exit_on_error=False)
        self.subparsers["help"].add_argument("command", type=str, nargs="?", help="The command to get help for")
        self.subparsers["help"].add_argument("subcommand", type=str, nargs="?", help="The subcommand to get help for")
        
        ## 'shutdown' command
        self.subparsers["shutdown"] = subparser_section.add_parser(ConsoleParser.Command.SHUTDOWN, help="Shuts down the Dedicated Server", description="Shuts down the Dedicated Server", add_help=False, exit_on_error=False)
        
        ## 'shutdown' command
        self.subparsers["restart"] = subparser_section.add_parser(ConsoleParser.Command.RESTART, help="Restarts the Dedicated Server", description="Restarts the Dedicated Server", add_help=False, exit_on_error=False)
        
        ## 'info' command
        self.subparsers["info"] = subparser_section.add_parser(ConsoleParser.Command.INFO, help="Gives information about the running Dedicated Server", description="Gives information about the running Dedicated Server", add_help=False, exit_on_error=False)
        
        ## 'kick' command
        self.subparsers["kick"] = subparser_section.add_parser(ConsoleParser.Command.KICK, help="Kicks a player from the server", description="Kicks a player from the server", add_help=False, exit_on_error=False)
        self.subparsers["kick"].add_argument("player", type=str, help="The GUID or name of the player to kick")
        
        ## 'whitelist' command
        self.subparsers["whitelist"] = subparser_section.add_parser(ConsoleParser.Command.WHITELIST, help="Manages/Queries the whitelist status", description="Manages/Queries whitelist status", add_help=False, exit_on_error=False)
        whitelist_section = self.subparsers["whitelist"].add_subparsers(parser_class=ArgumentParser, title="Sub-Command", description=None, dest="subcmd", type=ConsoleParser.WhitelistSubcommand, action=SubParserEnumStoreAction, required=True)
        
        self.subparsers["whitelist.enable"] = whitelist_section.add_parser(ConsoleParser.WhitelistSubcommand.ENABLE, add_help=False, exit_on_error=False, help="Enables the whitelist", description="Enables the whitelist")
        self.subparsers["whitelist.disable"] = whitelist_section.add_parser(ConsoleParser.WhitelistSubcommand.DISABLE, add_help=False, exit_on_error=False, help="Disables the whitelist", description="Disables the whitelist")
        self.subparsers["whitelist.status"] = whitelist_section.add_parser(ConsoleParser.WhitelistSubcommand.STATUS, add_help=False, exit_on_error=False, help="Queries the enabled status of the whitelist", description="Queries the enabled status of the whitelist")
        
        ## 'list' command
        self.subparsers["list"] = subparser_section.add_parser(ConsoleParser.Command.LIST, help="List players. Filter by provided category, if specified", description="List players. Filter by provided category, if specified", add_help=False, exit_on_error=False, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        self.subparsers["list"].add_argument("category", type=ConsoleParser.ListCategory, action=EnumStoreAction, default=ConsoleParser.ListCategory.ALL, nargs="?", help="The category to filter the output list on")
        
        ## 'savegame' command
        self.subparsers["savegame"] = subparser_section.add_parser(ConsoleParser.Command.SAVEGAME, help="Manages savegames", description="Manages savegames", add_help=False, exit_on_error=False)
        savegame_section = self.subparsers["savegame"].add_subparsers(parser_class=ArgumentParser, title="Sub-Command", description=None, dest="subcmd", type=ConsoleParser.SaveGameSubcommand, action=SubParserEnumStoreAction, required=True)
        
        self.subparsers["savegame.load"] = savegame_section.add_parser(ConsoleParser.SaveGameSubcommand.LOAD, add_help=False, exit_on_error=False, help="Loads a save and sets it as the active save for the server", description="Loads a save and sets it as the active save for the server")
        self.subparsers["savegame.load"].add_argument("save_name", type=str, help="The name of the save to load")
        
        self.subparsers["savegame.save"] = savegame_section.add_parser(ConsoleParser.SaveGameSubcommand.SAVE, add_help=False, exit_on_error=False, help="Saves the game instantly", description="Saves the game instantly")
        self.subparsers["savegame.save"].add_argument("save_name", type=str, nargs="?", help="The name to save the savegame as")
        
        self.subparsers["savegame.new"] = savegame_section.add_parser(ConsoleParser.SaveGameSubcommand.NEW, add_help=False, exit_on_error=False, help="Create a new save and set it as active", description="Create a new save and set it as active")
        self.subparsers["savegame.new"].add_argument("save_name", type=str, nargs="?",help="The name of the new save to create")
        
        self.subparsers["savegame.list"] = savegame_section.add_parser(ConsoleParser.SaveGameSubcommand.LIST, add_help=False, exit_on_error=False, help="List all the available savegames and marks the active one", description="List all the available savegames and marks the active one")

        ## 'player' command
        self.subparsers["player"] = subparser_section.add_parser(ConsoleParser.Command.PLAYER, help="Manages and shows Player Categories", description="Manages and shows Player Categories", add_help=False, exit_on_error=False)
        player_section = self.subparsers["player"].add_subparsers(parser_class=ArgumentParser, title="Sub-Command", description=None, dest="subcmd", type=ConsoleParser.PlayerSubcommand, action=SubParserEnumStoreAction, required=True)
        
        self.subparsers["player.set"] = player_section.add_parser(ConsoleParser.PlayerSubcommand.SET, add_help=False, exit_on_error=False, help="Sets the Category of a Player", description="Sets the Category of a Player")
        self.subparsers["player.set"].add_argument("player", type=str, help="The name or GUID of the player")
        self.subparsers["player.set"].add_argument("category", type=ConsoleParser.PlayerCategory, action=EnumStoreAction, help="The category to set the player to")
        
        self.subparsers["player.get"] = player_section.add_parser(ConsoleParser.PlayerSubcommand.GET, add_help=False, exit_on_error=False, help="Gets the Category of a Player", description="Gets the Category of a Player")
        self.subparsers["player.get"].add_argument("player", type=str, help="The name or GUID of the player")
    
    def get_help(self, cmd=None, subcmd=None):
        """
            Get help string for provided command (and subcommand)
            
            Arguments:
                - cmd: The command to get the help string of
                - subcmd: The subcommand to get the help string of
            
            Returns:
                - Status (bool): Wether a help message was found
                - Message (str): The message
        """
        
        # Cut out any dots from cmd and subcmd
        if isinstance(cmd, str):
            cmd = cmd.replace(".", "")
        
        if isinstance(subcmd, str):
            subcmd = subcmd.replace(".", "")
        
        # Return correct help string
        if (cmd == "") or (cmd is None):
            # No command provided, return general help
            return True, self.parser.format_help()
        elif cmd in self.subparsers:
            if (subcmd == "") or (subcmd is None):
                return True, self.subparsers[cmd].format_help()
            elif f"{cmd}.{subcmd}" in self.subparsers:
                return True, self.subparsers[f"{cmd}.{subcmd}"].format_help()
            else:
                return False, f"Subcommand '{subcmd}' for command '{cmd}' not found. See 'help {cmd}' for all subcommands"
        else:
            return False, f"Command '{cmd}' not found. See 'help' for all commands"
    
    def parse_input(self, input_string):
        """
            Parses the provided {input_string} using the command parser and returns wether it was successful and either the parameters or an error message
            
            Arguments:
                - input_string: The string to parse
            
            Returns:
                - Success (bool): Wether the parsing was successful
                - Result: One of the following
                    - If Success is True: Dictionary containing the parsed arguments
                    - If Success is False: An error message
        """
        
        # Split input by spaced but keep quoted strings together
        input_args = [re.sub(r"^\"(.*)\"$|^'(.*)'$", r"\1\2", t) for t in re.split(r" ?(\".*?\") ?| ?('.*?') ?| ", input_string) if (t is not None) and (t != "")]
        
        try:
            # Parse split input string using argument parser
            args = vars(self.parser.parse_args(input_args))
        except argparse.ArgumentError as e:
            if e.argument_name == "cmd":
                return False, f"Unknown command: {e.message}"
            elif e.argument_name == "subcmd":
                return False, f"Unknown subcommand: {e.message}"
            else:
                return False, str(e)
        except IllegalArgumentError as e:
            return False, e.message
        
        if args["cmd"] == ConsoleParser.Command.HELP:
            success, msg = self.get_help(args["command"], args["subcommand"])
            
            return (True, {"cmd": args["cmd"], "message": msg}) if success else (False, msg)
        else:
            # Add full command line to args for later use in messages
            args["cmdline"] = " ".join(input_args)
            
            return True, args


#
#   Logging
#

# Formats and colors
LOGFORMAT = "[%(asctime)s] [%(name)s/%(levelname)s] %(message)s"
CLOGFORMAT = "[%(asctime)s] %(log_color)s[%(name)s/%(levelname)s]%(reset)s %(message_log_color)s%(message)s"
DATEFORMAT = "%H:%M:%S"
LOGCOLORS = {
    "DEBUG":    "white",
    "INFO":     "green",
    "WARNING":  "yellow",
    "ERROR":    "red",
    "CRITICAL": "black,bg_red"
}
SECONDARY_LOG_COLORS = {
    "message": {
        "DEBUG":    "white",
        "INFO":     "light_white",
        "WARNING":  "yellow",
        "ERROR":    "red",
        "CRITICAL": "red"
    }
}

class LauncherLogging:
    """
        Class for managing logging. Can't be instantiated!
        
        Arguments:
            - log_debug: Wether to include log messages with level logging.DEBUG
    """
    
    log_debug = True
    
    handlers = {
            "out_console": None,
            "err_console": None,
            "logfile": None
        }
    
    logfile_path = None
    
    # Formatters
    colorformatter = colorlog.ColoredFormatter(CLOGFORMAT, datefmt=DATEFORMAT, log_colors=LOGCOLORS, secondary_log_colors=SECONDARY_LOG_COLORS)
    plainformatter = logging.Formatter(LOGFORMAT, datefmt=DATEFORMAT)
    
    def __new__(cls, *args, **kwargs):
        """ Override to prevent instantiation """
        raise TypeError(f"{cls.__name__} cannot be instantiated")
    
    @classmethod
    def prepare(cls):
        """ Prepares the logging module. Run this before the other setup methods """
        
        root_logger = logging.getLogger()
        
        # Remove default handler, if present
        if len(root_logger.handlers) > 0:
            root_logger.removeHandler(root_logger.handlers[0])
        
        root_logger.setLevel(logging.DEBUG)
    
    @classmethod
    def set_log_debug(cls, log_debug=True):
        """
            Set wether to log debug messages
            
            Arguments:
                - log_debug: Wether to include log messages with level logging.DEBUG
        """
        
        cls.log_debug = log_debug
        
        # Set levels for out_console and logfile handlers, but NOT for err_console handler
        level = logging.DEBUG if cls.log_debug else logging.INFO
        
        if cls.handlers["out_console"]:
            cls.handlers["out_console"].setLevel(level)
        
        if cls.handlers["logfile"]:
            cls.handlers["logfile"].setLevel(level)

    @staticmethod
    def get_logfile_path(log_path, base_filename=None, ending="log"):
        """
            Returns a path to a new logfile based upon a base {log_path}, a {base_filename} and a file {ending}
        """
        
        # If path is not a directory, raise error
        if not os.path.isdir(log_path):
            raise ValueError("Log Path is not a directory")
        
        datetime_string = datetime.today().strftime("%Y-%m-%d")
        
        base_string=""
        
        # base filename can be None, in which case it is completely omitted
        if not (base_filename is None):
            base_string = f"{base_filename}_"
        
        log_filename= f"{base_string}{datetime_string}"
        
        # If file with name already exists, add increasing integer until free file is found
        i = 1
        logfile_path = os.path.join(log_path, f"{log_filename}.{ending}")
        
        while os.path.exists(logfile_path):
            # Failsave to not create endless loop
            if i > 1000000:
                raise FileExistsError("All log files with added integers up to 1000000 already exist, what are you doing?!")
            
            logfile_path = os.path.join(log_path, f"{log_filename}_{i}.{ending}")
            i += 1

        return logfile_path
    
    @classmethod
    def setup_console(cls):
        """
            Setup (colored) logging formats for console output using the logging module
        """
        
        # Initialize handler for standard out (Non-error console)
        cls.handlers["out_console"] = logging.StreamHandler(sys.stdout)
        cls.handlers["out_console"].setFormatter(cls.colorformatter)
        cls.handlers["out_console"].setLevel(logging.DEBUG if cls.log_debug else logging.INFO)
        cls.handlers["out_console"].addFilter(lambda record: record.levelno <= logging.WARNING)
        
        logging.getLogger().addHandler(cls.handlers["out_console"])
        
        # Initialize handler for standard error (Error console)
        cls.handlers["err_console"] = logging.StreamHandler(sys.stderr)
        cls.handlers["err_console"].setFormatter(cls.colorformatter)
        cls.handlers["err_console"].setLevel(logging.ERROR)
        
        logging.getLogger().addHandler(cls.handlers["err_console"])
    
    @classmethod
    def setup_logfile(cls, log_path):
        """
            Setup logging formats for log file output using the logging module
            
            Arguments:
                - log_path: Path to a directory to store logs at
        """
            
        # Create logfile path if not existing yet
        if not os.path.exists(log_path):
            os.makedirs(log_path)

        logfile_path = LauncherLogging.get_logfile_path(log_path, "astrotux")

        cls.handlers["logfile"] = logging.FileHandler(logfile_path)
        cls.handlers["logfile"].setFormatter(cls.plainformatter)
        cls.handlers["logfile"].setLevel(logging.DEBUG if cls.log_debug else logging.INFO)

        logging.getLogger().addHandler(cls.handlers["logfile"])
        
        cls.logfile_path = logfile_path

#
#   Notifications
#

class EventType(Enum):
    MESSAGE = "message"
    START = "start"
    REGISTERED = "registered"
    SHUTDOWN = "shutdown"
    CRASH = "crash"
    PLAYER_JOIN = "player_join"
    PLAYER_LEAVE = "player_leave"
    COMMAND = "command"
    SAVE = "save"
    SAVEGAME_CHANGE = "savegame_change"

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


def safeformat(string, keep_escape=True, **kwargs):
    """
        Formats the passed string {str} using the given keyword arguments, while keeping missing replacements unformatted
    """
    
    class SafeDict(dict):
        def __missing__(self, key):
            return '{' + key + '}'
        
    replacements = SafeDict(**kwargs)
    
    # Keep escaped strings
    if keep_escape:
        string = string.replace("{{", "{{{{").replace("}}", "}}}}")
    
    return string.format_map(replacements)

DEFAULT_EVENT_FORMATS = {
        EventType.MESSAGE           : "{message}",
        EventType.START             : "Server started!",
        EventType.REGISTERED        : "Server registered with Playfab!",
        EventType.SHUTDOWN          : "Server shutting down...",
        EventType.CRASH             : "Server crashed!",
        EventType.PLAYER_JOIN       : "Player '{player_name}'({player_guid}) joined the game",
        EventType.PLAYER_LEAVE      : "Player '{player_name}'({player_guid}) left the game",
        EventType.COMMAND           : "Command executed: {command}",
        EventType.SAVE              : "Game saved!",
        EventType.SAVEGAME_CHANGE   : "Savegame changed to '{savegame_name}'"
    }


# Parent classes

class NotificationHandler:
    """
        A class that can receive events and send them along as formatted messages to some endpoint
        
        Arguments:
            - name: A string identifying the handler
            - event_whitelist: Events whose event is in this list are passed on as messages, else, events are discarded
            - event_formats: Dictionary mapping EventType's to format strings that are used while formatting the message to pass on
    """
    
    def __init__(self, name="Notification", event_whitelist=set([e for e in EventType]), event_formats=DEFAULT_EVENT_FORMATS):
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
        
        Arguments:
            - name: see NotificationHandler class
            - event_whitelist: see NotificationHandler class
            - event_formats: see NotificationHandler class
    """
    
    class NotificationThread(threading.Thread):
        def __init__(self, callback, name="notification-thread"):
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
        
        self.thread = QueuedNotificationHandler.NotificationThread(self._send_message)
    
    def send_event(self, event_type=EventType.MESSAGE, **params):
        """ Send event using the provided parameters """
        
        # Only send, if event is in whitelist
        if event_type in self.whitelist:
            # Add server name to parameters for formatting
            params["name"] = self.name
            message = safeformat(self.formats[event_type], **params)
            
            self.thread.add_event(event_type, message)
    
    def _send_message(self, event_type, message):
        """
            Method for handling events asynchronously.
            To be overritten by subclasses.
        """
        
        time.sleep(3)
        print(message)

DEFAULT_LEVEL_MAPPING = {
        EventType.MESSAGE           : logging.INFO,
        EventType.START             : logging.INFO,
        EventType.REGISTERED        : logging.INFO,
        EventType.SHUTDOWN          : logging.INFO,
        EventType.CRASH             : logging.WARNING,
        EventType.PLAYER_JOIN       : logging.INFO,
        EventType.PLAYER_LEAVE      : logging.INFO,
        EventType.COMMAND           : logging.INFO,
        EventType.SAVE              : logging.INFO,
        EventType.SAVEGAME_CHANGE   : logging.INFO
    }

LOGGING_DEFAULT_EVENT_WHITELIST = set([
        EventType.MESSAGE,
        EventType.START,
        EventType.REGISTERED,
        EventType.SHUTDOWN,
        EventType.CRASH,
        EventType.PLAYER_JOIN,
        EventType.PLAYER_LEAVE,
        EventType.SAVE,
        EventType.SAVEGAME_CHANGE
])

class LoggingNotificationHandler(NotificationHandler):
    """
        Notification handler that logs events using the logging module
        
        Arguments:
            - name: see NotificationHandler class
            - event_whitelist: see NotificationHandler class
            - event_formats: see NotificationHandler class
            - level_mapping: Mapping from EventType to a logging level
    """
    
    def __init__(self, name="Server", event_whitelist=LOGGING_DEFAULT_EVENT_WHITELIST, event_formats=DEFAULT_EVENT_FORMATS, level_mapping=DEFAULT_LEVEL_MAPPING):
        super().__init__(name, event_whitelist, event_formats)
        
        self.level_mapping = level_mapping
        
        self.logger = logging.getLogger("Notify")
    
    def _send_message(self, event_type, message):
        level = self.level_mapping[event_type]
        
        self.logger.log(level, message)

DISCORD_MESSAGE_TEMPLATE = """{{
    "content": null,
    "embeds": [
        {{
            "title": ":{emoji}: {message}",
            "color": {color},
            "fields": [
                {{
                    "name": "Event",
                    "value": "{event_type}",
                    "inline": true
                }},
                {{
                    "name": "Version",
                    "value": "{server_version}",
                    "inline": true
                }}
            ],
            "author": {{
                "name": "Server Notification"
            }},
            "footer": {{
                "text": "AstroTuxLauncher v{launcher_version}"
            }},
            "timestamp": "{timestamp}"
        }}
    ],
    "username": "{name}",
    "avatar_url": "https://astroneer.wiki.gg/images/7/74/Icon_Astroneer.png",
    "attachments": [],
    "flags": 4096
}}"""

DISCORD_HEADERS = {
    'content-type': 'application/json; charset=utf-8',
    'User-Agent': f"AstroTuxLauncher/{LAUNCHER_VERSION}",
    'Accept': 'application/json'
}

DISCORD_EVENT_EXTRA_MAPPING = {
    EventType.MESSAGE           : {"color": 10526880,   "emoji": "information_source"},
    EventType.START             : {"color": 3256064,    "emoji": "green_square"},
    EventType.REGISTERED        : {"color": 10526880,   "emoji": "white_check_mark"},
    EventType.SHUTDOWN          : {"color": 14440960,   "emoji": "orange_square"},
    EventType.CRASH             : {"color": 13764616,   "emoji": "red_square"},
    EventType.PLAYER_JOIN       : {"color": 41160,      "emoji": "inbox_tray"},
    EventType.PLAYER_LEAVE      : {"color": 6553800,    "emoji": "outbox_tray"},
    EventType.COMMAND           : {"color": 15118080,   "emoji": "wrench"},
    EventType.SAVE              : {"color": 7274240,    "emoji": "file_cabinet"},
    EventType.SAVEGAME_CHANGE   : {"color": 15118080,   "emoji": "dividers"}
}

class DiscordNotificationHandler(QueuedNotificationHandler):
    """
        Queued Notification handler that sends event messages to a discord webhook
    """
    
    def __init__(self, webhook_url, name="Server", event_whitelist=set([e for e in EventType]), event_formats=DEFAULT_EVENT_FORMATS, extra_formats=DISCORD_EVENT_EXTRA_MAPPING):
        self.webhook_url = webhook_url
        self.extra_mapping = extra_formats
        
        # This is to prevent overriding default constants
        event_formats = event_formats.copy()
        
        # Add message formats to Discord Message template
        for et in EventType:
            event_formats[et] = safeformat(DISCORD_MESSAGE_TEMPLATE, message=event_formats[et])
        
        super().__init__(name, event_whitelist, event_formats)
        
        self.logger = logging.getLogger("DiscordNotify")
        
        self.logger.debug(f"Event Whitelist: {list(self.whitelist)}")
    
    def _send_message(self, event_type, message):
        extra = self.extra_mapping[event_type]
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        message_json = safeformat(message, keep_escape=False, event_type=event_type.value, color=extra["color"], emoji=extra["emoji"], launcher_version=LAUNCHER_VERSION, timestamp=timestamp)
        
        # Normalize JSON
        message_json = json.loads(message_json)
        
        try:
            resp = net.post_request(self.webhook_url, headers=DISCORD_HEADERS, jsonData=message_json)
        except Exception as e:
            self.logger.error(f"Error while sending Discord notification: {str(e)}")

NTFY_MESSAGE_TEMPLATE = """{{
    "topic": "{topic}",
    "message": "{name}",
    "title": "{message}",
    "tags": [
        "{emoji}",
        "{event_type}",
        "AstroTuxLauncher"
    ],
    "priority": {priority}
}}"""

NTFY_HEADERS = {
    'content-type': 'application/json; charset=utf-8',
    'User-Agent': f"AstroTuxLauncher/{LAUNCHER_VERSION}",
    'Accept': 'application/json'
}

NTFY_EVENT_EXTRA_MAPPING = {
    EventType.MESSAGE           : {"priority": 2, "emoji": "information_source"},
    EventType.START             : {"priority": 4, "emoji": "green_square"},
    EventType.REGISTERED        : {"priority": 3, "emoji": "white_check_mark"},
    EventType.SHUTDOWN          : {"priority": 4, "emoji": "orange_square"},
    EventType.CRASH             : {"priority": 5, "emoji": "red_square"},
    EventType.PLAYER_JOIN       : {"priority": 3, "emoji": "inbox_tray"},
    EventType.PLAYER_LEAVE      : {"priority": 3, "emoji": "outbox_tray"},
    EventType.COMMAND           : {"priority": 3, "emoji": "wrench"},
    EventType.SAVE              : {"priority": 2, "emoji": "file_cabinet"},
    EventType.SAVEGAME_CHANGE   : {"priority": 2, "emoji": "card_index_dividers"}
}

class NTFYNotificationHandler(QueuedNotificationHandler):
    """
        Queued Notificationm handler that sends event messages to an ntfy instance
    """
    
    def __init__(self, topic, ntfy_url="https://ntfy.sh", name="Server", event_whitelist=set([e for e in EventType]), event_formats=DEFAULT_EVENT_FORMATS, extra_formats=NTFY_EVENT_EXTRA_MAPPING):
        self.topic = topic
        self.ntfy_url = ntfy_url
        self.extra_mapping = extra_formats
        
        # This is to prevent overriding default constants
        event_formats = event_formats.copy()
        
        # Add message formats to Discord Message template
        for et in EventType:
            event_formats[et] = safeformat(NTFY_MESSAGE_TEMPLATE, message=event_formats[et], topic=self.topic)
        
        super().__init__(name, event_whitelist, event_formats)
        
        self.logger = logging.getLogger("NTFYNotify")
        
        self.logger.debug(f"Event Whitelist: {list(self.whitelist)}")
    
    def _send_message(self, event_type, message):
        extra = self.extra_mapping[event_type]
        
        message_json = safeformat(message, keep_escape=False, event_type=event_type.value, priority=extra["priority"], emoji=extra["emoji"])
        
        # Normalize JSON
        message_json = json.loads(message_json)
        
        try:
            resp = net.post_request(self.ntfy_url, headers=NTFY_HEADERS, jsonData=message_json)
        except Exception as e:
            self.logger.error(f"Error while sending ntfy notification: {str(e)}")

#
#   Miscellaneous
#

PROC_FORMAT="[{name}] {message}"

def run_proc_with_logging(args, name, format=PROC_FORMAT, sleep_time=0.05, level=logging.INFO, alive_bar=None, **popen_args):
    """ Runs a process and outputs its output using the logging module and waits for it to finish """
    
    # Create process with piped stdout/stderr
    process = subprocess.Popen(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=1, close_fds=True, text=True, **popen_args)
    
    def enqueue_output(out, queue):
        """ Reads lines from {out} and adds them to {queue} """
        for line in iter(out.readline, b''):
            queue.put(line)
        out.close()
    
    # Output queue
    out_queue = Queue()
    
    # Thread for adding to the queue asynchronously
    read_thread = threading.Thread(target=enqueue_output, args=(process.stdout, out_queue))
    read_thread.daemon = True
    read_thread.start()
    
    # Wait until process is finished and handle output
    while process.poll() is None:
        try:
            line = out_queue.get_nowait()
        except Empty:
            # If queue is empty, simply pass on
            pass
        else:
            line = line.replace("\n", "")   # Remove newline character, since it it unnecessary
            LOGGER.log(level, safeformat(format, name=name, message=line))
        
        if alive_bar:
            alive_bar()
        
        time.sleep(sleep_time)
    
    return process.poll()


# Class for sending regular status updates to an http endpoint
class StatusUpdaterThread(threading.Thread):
    def __init__(self, base_url, status=True, message=None, timeout=120, status_mapping={True: "up", False: "down"}, parameter_name_map={"message": "msg", "status": "status"}, name="status-updater-thread"):
        self.base_url = base_url
        self.status = bool(status)
        self.status_mapping = status_mapping
        self.param_map = parameter_name_map
        self.curr_msg = str(message)
        self.timeout = int(timeout)
        
        self._update_event = threading.Event()
        self._stop_event = threading.Event()
        self.logger = logging.getLogger(name)
        
        super(StatusUpdaterThread, self).__init__(name=name)
        self.daemon = True
    
    def stop(self):
        self._stop_event.set()
    
    def stopped(self):
        return self._stop_event.is_set()
    
    def update_status(self, status, message=None):
        changed = False
        
        if bool(status) != self.status:
            changed = True
            self.status = bool(status)
        
        if (message is not None) and (str(message) != self.curr_msg):
            changed = True
            self.curr_msg = str(message)
        
        # If something changed, trigger sending of status update
        if changed:
            self._update_event.set()
    
    def _send_current_status(self):
        """ Sends a status update to the endpoint and returns the success as a boolean """
        
        if self.curr_msg is None:
            paramstring = urlparse.urlencode({
                self.param_map['status']: self.status_mapping[self.status],
            })
        else:
            paramstring = urlparse.urlencode({
                self.param_map['status']: self.status_mapping[self.status],
                self.param_map['message']: self.curr_msg,
            })
        
        url = requote_uri(f"{self.base_url}?{paramstring}")
        
        try:
            resp = net.get_request(url)
        except TimeoutError:
            self.logger.warning("Timeout while sending status update")
            return False
        except Exception as e:
            self.logger.error(f"Error while sending status update: {str(e)}")
            return False
        
        try:
            is_ok = json.load(resp)["ok"]
            
            if is_ok == False:
                self.logger.warning("Status Endpoint returned not-ok status")
            
            return is_ok
        except Exception as e:
            self.logger.error(f"Invalid response: {str(resp)}")
            return False
    
    def run(self):
        """ Sends status update and waits for either event to fire or timeout seconds """
        
        while True:
            # Exit the loop, if requested to stop
            if self._stop_event.is_set():
                break
            
            # Send actual status update
            self._send_current_status()
            
            
            # Wait until update event fires or timeout seconds
            self._update_event.wait(timeout=self.timeout)
            self._update_event.clear()