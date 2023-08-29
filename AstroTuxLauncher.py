#!/usr/bin/python3

import os
from os import path
import argparse
import json
import tomli, tomli_w
import dataclasses
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config
from typing import Optional
from utils.misc import ExcludeIfNone, read_build_version
from utils.termutils import set_window_title
from enum import Enum
from pansi import ansi
import utils.interface as interface
import logging
import sys
from queue import Queue
import shutil
from utils import steam
from utils.net import get_request
from packaging import version
import astro.playfab as playfab
from astro.dedicatedserver import AstroDedicatedServer, ServerStatus
import utils.net as net
import signal
import subprocess
import time


"""
Code based on https://github.com/ricky-davis/AstroLauncher
"""

BANNER_LOGO = f"""{ansi.weight.bold}
    {ansi.BLUE}___         __           {ansi.YELLOW}______          
   {ansi.BLUE}/   |  _____/ /__________{ansi.YELLOW}/_  __/_  ___  __
  {ansi.BLUE}/ /| | / ___/ __/ ___/ __ \{ansi.YELLOW}/ / / / / / |/_/
 {ansi.BLUE}/ ___ |(__  ) /_/ /  / /_/ {ansi.YELLOW}/ / / /_/ />  <  
{ansi.BLUE}/_/  |_/____/\__/_/   \____{ansi.YELLOW}/_/  \__,_/_/|_|  {ansi.reset}
"""
BANNER_SUBTITLE = "L a u n c h e r".center(45)

BANNER_TEXT="Unofficial Astroneer Dedicated Server Launcher for Linux"


#
#   Constants
#

VERSION = "0.0.1"
NAME = "AstroTuxLauncher"

HELP_COMMAND = f"""What {NAME} should do

    - install: Installs the Astroneer Dedicated Server using steamcmd
    - start: Starts the installed dedicated server
    - update: Updates the Astroneer Dedicated Server using steamcmd
"""

DEPOTDL_PATH = "libs/depotdownloader"
DS_EXECUTABLE = "AstroServer.exe"

ASTRO_SERVER_STATS_URL = "https://servercheck.spycibot.com/stats"

class LauncherCommand(Enum):
    """ Represents the command passed to the launcher """
    
    START = "start"
    INSTALL = "install"
    UPDATE = "update"



#
#   Configuration classes
#

class NotificationMethod(Enum):
    """ Represents, which notification method should be used """
    
    NONE = ""
    NTFY = "ntfy"
    DISCORD = "discord"

@dataclass
class DiscordConfig:
    webhookURL: str = None

@dataclass
class NTFYConfig:
    topic: str = None
    server: str = "https://ntfy.sh"

@dataclass
class NotificationConfig:
    method: NotificationMethod = NotificationMethod.NONE
    
    dicsord: Optional[DiscordConfig] =  field(metadata=config(exclude=ExcludeIfNone), default=None)
    ntfy: Optional[NTFYConfig] =  field(metadata=config(exclude=ExcludeIfNone), default=None)

@dataclass_json
@dataclass
class LauncherConfig:
    AutoUpdateServer: bool = True   # Wether to automatically install/update the Astroneer DS at start if update is available
    
    CheckNetwork: bool = True       # Wether to perform a network check before starting the Astroneer DS
    OverwritePublicIP: bool = False # Wether to overwrite the PublicIP DS config option with the fetched public IP
    
    # Settings related to notifications
    notifications: NotificationConfig = NotificationConfig()    # Configuration for notifications
    
    LogDebugMessages: bool = False  # Wether the the console and log file should include log messages with level logging.DEBUG
    
    AstroServerPath: str = "AstroneerServer"    # The path, where the Astroneer DS installation should reside
    OverrideWinePath: Optional[str] = field(metadata=config(exclude=ExcludeIfNone), default=None)   # Path to wine executable, only used, if set
    WinePrefixPath: str = "winepfx"             # The path, where the Wine prefix should be stored
    LogPath: str = "logs"                       # The path where logs should be saved
    
    PlayfabAPIInterval: int = 2                 # Time to wait between Playfab API requests
    ServerStatusInterval: float = 3             # Time to wait between Server Status checks
    
    DisableEncryption: bool = True  # Wether to disable encryption for the Astroneer DS. CURRENTLY REQUIRED TO BE "True" FOR HOSTING ON LINUX
        
    @staticmethod
    def ensure_toml_config(config_path):
        """
            Reads the launcher configuration and fist creates the config file if not present, populated with the default values
        """
        
        config = None
        
        if path.exists(config_path):
            # If config file exists, read it into a config object
            if not path.isfile(config_path):
                raise ValueError("Specified config path doesn't point to a file!")
            
            with open(config_path, "rb") as tf:
                toml_dict = tomli.load(tf)
            
            # If no "launcher" section is present in the file, create it as empty
            if not ("launcher" in toml_dict.keys()):
                toml_dict = {"launcher": {}}
            
            config = LauncherConfig.from_dict(toml_dict["launcher"])

        else:
            # If config file is not present, create directories and default config
            if not path.exists(path.dirname(config_path)):
                os.makedirs(path.dirname(config_path))
            
            config = LauncherConfig()
        
        # Write config back to file to add missing entried and remove superflous ones
        # In the case of the file not existing prior, it will be created
        config_dict = {"launcher": config.to_dict(encode_json=True)}
        
        with open(config_path, "wb") as tf:
            tomli_w.dump(config_dict, tf)
        
        return config

class AstroTuxLauncher():
    
    def __init__(self, config_path, astro_path, depotdl_exec):
        # Setup basic logging
        interface.LauncherLogging.prepare()
        interface.LauncherLogging.setup_console()
        
        try:
            self.config_path = path.abspath(config_path)
            
            logging.info(f"Configuration file path: {self.config_path}")
            
            self.config = LauncherConfig.ensure_toml_config(self.config_path)
        except Exception as e:
            logging.error(f"Error while loading config file ({type(e).__name__}): {str(e)}")
            logging.error(f"Please check the config path parameter and/or config file")
            self.exit()
        
        # If cli parameter is specified, it overrides the config value
        if not (astro_path is None):
            self.config = dataclasses.replace(self.config, {"AstroServerPath": astro_path})
        
        # Make sure we use absolute paths
        self.config.AstroServerPath = path.abspath(self.config.AstroServerPath)
        self.config.WinePrefixPath = path.abspath(self.config.WinePrefixPath)
        self.config.LogPath = path.abspath(self.config.LogPath)
        
        # Apply wine path override if possible and check that is exists
        self.wineexec = shutil.which("wine")
        self.wineserverexec = shutil.which("wineserver")
        
        if self.config.OverrideWinePath is not None and path.isfile(self.config.OverrideWinePath):
            self.wineexec = path.abspath(self.config.OverrideWinePath)
            self.wineserverexec = path.join(path.dirname(self.wineexec), "wineserver")
        
        if (self.wineexec is None) or (self.wineserverexec is None):
            logging.error("Wine (or Wineserver) executable not found!")
            logging.error("Make sure that you have wine installed and accessible")
            logging.error("or set 'OverrideWinePath' config option to the path of the wine executable")
            self.exit()
        
        # Finish setting up logging
        interface.LauncherLogging.set_log_debug(self.config.LogDebugMessages)
        interface.LauncherLogging.setup_logfile(self.config.LogPath)
        
        self.launcherPath = os.getcwd()
        
        self.depotdl_path = None
        
        # If argument is given, file has to exist
        if depotdl_exec:
            # If {depotdl_exec} is a command, get full path
            wpath = shutil.which(depotdl_exec)
            if wpath is not None:
                depotdl_exec = wpath
            
            if path.isfile(depotdl_exec):
                self.depotdl_path = path.abspath(depotdl_exec)
                logging.info(f"DepotDownloader path overridden: {self.depotdl_path}")
        
        # If argument is not given, default path is used and may not exists yet, so create directories
        if self.depotdl_path is None:
            self.depotdl_path = path.abspath(DEPOTDL_PATH)
            os.makedirs(path.dirname(self.depotdl_path), exist_ok=True)
        
        # Log some information about loaded paths, configs, etc.
        logging.info(f"Working directory: {self.launcherPath}")
        logging.debug(f"Launcher configuration (including overrides):\n{json.dumps(self.config.to_dict(encode_json=True), indent=4)}")
        
        # Initialize console command parser
        self.console_parser = interface.ConsoleParser()
        self.cmd_queue = Queue()
        
        # Initialize Input Thread to handle console input later. Don't start thread just yet
        self.input_thread = interface.KeyboardThread(self.on_input, False)
        
        # Initialize notification objects
        self.notifications = interface.NotificationManager()
        
        self.notifications.add_handler(interface.LoggingNotificationHandler())
        #TODO: Initialize Webhook handlers
        
        # Create Dedicated Server object
        #TODO: Maybe move to stert_server
        self.dedicatedserver = AstroDedicatedServer(self)
    
    def check_ds_executable(self):
        """ Checks is Astroneer DS executable exists and is a file """
        
        execpath = os.path.join(self.config.AstroServerPath, DS_EXECUTABLE)
        
        return os.path.exists(execpath) and os.path.isfile(execpath)

    def on_input(self, input_string):
        """ Callback method to handle console input """
        
        # Parse console input
        success, result = self.console_parser.parse_input(input_string)
        
        if success:
            if result["cmd"] == interface.ConsoleParser.Command.HELP:
                # If it's a help command, we don't need to add it to the command queue as there is nothing to be done
                logging.info(result["message"])
            else:
                # Add any other command to the command queue to be processed later
                self.cmd_queue.put(result)
        else:
            # If an error occured, {result} is just a message, so log it to console
            # We send event for command first, when it's processed
            logging.warning(result)

    def update_wine_prefix(self):
        """
            Creates/updated the WINE prefix
        """
        
        logging.debug("Creating/updating WINE prefix...")
        
        cmd = [self.wineexec, "wineboot"]
        env = os.environ.copy()
        
        # Remove DISPLAY environment variable to stop wine from creating a window
        if "DISPLAY" in env:
            del env["DISPLAY"]
        
        env["WINEPREFIX"] = self.config.WinePrefixPath
        env["WINEDEBUG"] = "-all"
        
        try:
            wineprocess = subprocess.Popen(cmd, env=env, cwd=self.config.AstroServerPath, stderr=subprocess.PIPE, stdout=subprocess.PIPE, close_fds=True)
            code = wineprocess.wait(timeout=30)
        except TimeoutError:
            logging.debug("Wine process took longer than 30 seconds, aborting")
            return False
        except Exception as e:
            logging.error(f"Error occured during updating of wine prefix: {str(e)}")
            return False
        
        return code == 0    
    
    def check_network_config(self):
        if not self.dedicatedserver:
            raise ValueError("Dedcated Server has to be created first")
        
        # Check if server port is reachable from local network over UDP
        server_local_reachable = net.net_test_local(self.dedicatedserver.ds_config.PublicIP, self.dedicatedserver.engine_config.Port, False)
        
        # Check if server post is reachable from internet over UDP
        server_nonlocal_reachable = net.net_test_nonlocal(self.dedicatedserver.ds_config.PublicIP, self.dedicatedserver.engine_config.Port)
        
        test_res = (server_local_reachable, server_nonlocal_reachable)
        
        logging.debug(f"Test Matrix: {str(test_res)}")
        
        if test_res == (True, True):
            logging.info("Network configuration looks good")
        elif test_res == (False, True):
            logging.warning("The Server is not accessible from the local network")
            logging.warning("This usually indicates an issue with NAT Loopback")
        elif test_res == (True, False):
            logging.warning("The server can be reached locally, but not from outside of the local network")
            logging.warning(f"Make sure the Server Port ({self.dedicatedserver.engine_config.Port}) is forwarded for UDP traffic")
        elif test_res == (False, False):
            logging.warning("The Server is completely unreachable")
            logging.warning(f"Make sure the Server Port ({self.dedicatedserver.engine_config.Port}) is forwarded for UDP traffic and check firewall settings")
        
        rcon_local_blocked = not net.net_test_local(self.dedicatedserver.ds_config.PublicIP, self.dedicatedserver.ds_config.ConsolePort, True)
        
        if rcon_local_blocked:
            logging.info("RCON network configuration looks good")
        else:
            logging.warning(f"SECURITY ALERT: The RCON Port ({self.dedicatedserver.ds_config.ConsolePort}) is accessible from outside")
            logging.warning("SECURITY ALERT: This potentially allows access to the Remote Console from outside your network")
            logging.warning("SECURITY ALERT: Disable this ASAP to prevent issues")
            
            # kept from AstroLauncher
            time.sleep(5)
    
    def update_server(self):
        """
            Installs/Updates the Astroneer Dedicated Server.
            Also ensures that DepotDownloader is present
        """
        
        # If DepotDownloader executable doesn't exists yet, download it
        if not path.exists(self.depotdl_path):
            logging.info("Downloading DepotDownloader...")
            steam.dl_depotdownloader(path.dirname(self.depotdl_path), path.basename(self.depotdl_path))
        
        logging.info("Downloading Astroneer Dedicated Server...")
        success = steam.update_app(exec_path=self.depotdl_path, app="728470", os="windows", directory=self.config.AstroServerPath)
        
        self.buildversion = read_build_version(self.config.AstroServerPath)
        
        if success and (self.buildversion is not None):
            logging.info(f"Sucessfully downloaded Astroneer Dedicated Server version {self.buildversion}")
        else:
            logging.error("Error while downloading Astroneer Dedicated Server")
    
    def check_server_update(self, force_update=False):
        """
            Checks if an update for the Astroneer Dedicated Server is available or if it needs to be installed.
            Also performs update if set in config or {force_update} is set to True
        """
        
        oldversion = read_build_version(self.config.AstroServerPath)
        
        do_update = False
        installed = True
        
        if (oldversion is None) or not self.check_ds_executable():
            # No version is present yet or executable not present, we need an update/installation
            logging.warning("Astroneer Dedicated Server is not installed yet")
            do_update = True
            installed = False
        else:
            # Get current server version from Spycibot endpoint
            try:
                data = json.load(get_request(ASTRO_SERVER_STATS_URL))
                newversion = data["LatestVersion"]
                
                if version.parse(newversion) > version.parse(oldversion):
                    logging.warn(f"Astroneer Dedicated Server update available ({oldversion} -> {newversion})")
                    do_update = True
            except Exception as e:
                logging.error(f"Error occured while checking for newest version: {str(e)}")

        if do_update:
            if self.config.AutoUpdateServer:
                if installed:
                    logging.info("Automatically updating server")
                else:
                    logging.info("Automatically installing server")
            
            if self.config.AutoUpdateServer or force_update:
                self.update_server()
            else:
                logging.info("Not installing/updating automatically")
        else:
            if force_update:
                logging.info("Nothing to do")
        
    def start_server(self):
        """
            Starts the Astroneer Dedicated Server after setting up environment
        """
        
        # Check for and install DS update if wanted
        self.check_server_update()
        
        # If Playfab API can't be reached, we can't continue
        if not playfab.check_api_health():
            logging.error("Playfab API is unavailable. Are you connected to the internet?")
            self.exit(reason="Playfab API unavailable")
        
        # Make sure wine prefix is ready
        if not self.update_wine_prefix():
            self.exit(reason="Error while updating WINE prefix")
        
        # Check that ports are available for the Server and RCON
        if not self.dedicatedserver.check_ports_free():
            self.exit(reason="Port not available")
        
        # Check netowrk configuration
        if self.config.CheckNetwork:
            self.check_network_config()
        
        self.input_thread.start()
        
        # Prepare and start dedicated server
        try:
            self.dedicatedserver.start()
        except Exception as e:
            logging.error(f"There as an error while starting the Dedicated Server: {str(e)}")
            self.exit(reason="Error while starting Dedicated Server")
        
        logging.debug("Activating input thread...")
        self.input_thread.set_active(True)
        
        logging.debug("Starting server loop...")
        # Run Server Loop
        self.dedicatedserver.server_loop()
        
        logging.debug("Server loop finished")
    
    
    def user_exit(self, signal, frame):
        """ Callback for when user requests to exit the application """
        self.exit(graceful=True, reason="User Requested to exit")
    
    def exit(self, graceful=False, reason=None):
        if self.dedicatedserver and self.dedicatedserver.status == ServerStatus.RUNNING:
            if graceful:
                self.dedicatedserver.shutdown()
                return
            else:
                self.dedicatedserver.kill()
        
        if reason:
            logging.info(f"Quitting... (Reason: {reason})")
        else:
            logging.info("Quitting...")
        
        sys.exit(0 if graceful else 1)

if __name__ == "__main__":
    # Set terminal window title
    set_window_title(f"{NAME} - Unofficial Astroneer Dedicated Server Launcher for Linux")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("command", type=LauncherCommand, action=interface.EnumStoreAction, help=HELP_COMMAND)
    parser.add_argument("-c", "--config_path", help="The location of the configuration file (default: %(default)s)", type=str, dest="config_path", default="launcher.toml")
    parser.add_argument("-p", "--astro_path", help="The path of the Astroneer Dedicated Server installation (default: %(default)s)", dest="astro_path", default=None)
    parser.add_argument("-d", "--depotdl_exec", help="The path to anm existing depotdownloader executable (default: %(default)s)", dest="depotdl_exec", default=None)
        
    args = parser.parse_args()
    
    # Print Banner
    print(BANNER_LOGO, end="")
    print(BANNER_SUBTITLE)
    print("")
    print(BANNER_TEXT)
    print(f"v{VERSION}")
    print("")
    
    try:
        launcher = AstroTuxLauncher(args.config_path, args.astro_path, args.depotdl_exec)
    except KeyboardInterrupt:
        print("Quitting... (requested by user)")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, launcher.user_exit)
    
    if args.command == LauncherCommand.INSTALL:
        logging.info("Installing Astroneer Dedicated Server...")
        launcher.update_server()
    elif args.command == LauncherCommand.UPDATE:
        logging.info("Checking for available updates to the Astroneer Dedicated Server...")
        launcher.check_server_update(force_update=True)
    elif args.command == LauncherCommand.START:
        logging.info("Starting Astroneer Dedicated Server")
        launcher.start_server()
    
    logging.debug("Application finished")