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
from utils.misc import ExcludeIfNone
from utils.termutils import set_window_title
from enum import Enum
from pansi import ansi
import utils.interface as interface
import logging
import sys

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

DEPOTDL_PATH = "depotdownloader"


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
    AutoInstallServer: bool = False # Wether to automatically install the Astroneer DS at start if not found
    AutoUpdateServer: bool = True   # Wether to automatically update the Astroneer DS at start if update is available
    
    CheckNetwork: bool = True       # Wether to perform a network check before starting the Astroneer DS
    OverwritePublicIP: bool = False # Wether to overwrite the PublicIP DS config option with the fetched public IP
    
    # Settings related to notifications
    notifications: NotificationConfig = NotificationConfig()    # Configuration for notifications
    
    LogDebugMessages: bool = False  # Wether the the console and log file should include log messages with level logging.DEBUG
    
    AstroServerPath: str = "AstroneerServer"    # The path, where the Astroneer DS installation should reside
    OverrideWinePath: Optional[str] = field(metadata=config(exclude=ExcludeIfNone), default=None)   # Path to wine executable, only used, if set
    WinePrefixPath: str = "winepfx"             # The path, where the Wine prefix should be stored
    LogPath: str = "logs"                       # The path where logs should be saved
    
    
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
    
    def __init__(self, config_path, astro_path, depotdl_path):
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
            sys.exit()
        
        # If cli parameter is specified, it overrides the config value
        if not (astro_path is None):
            self.config = dataclasses.replace(self.config, {"AstroServerPath": astro_path})
        
        # Make sure we use absolute paths
        self.config.AstroServerPath = path.abspath(self.config.AstroServerPath)
        self.config.WinePrefixPath = path.abspath(self.config.WinePrefixPath)
        self.config.LogPath = path.abspath(self.config.LogPath)
        
        # Finish setting up logging
        interface.LauncherLogging.set_log_debug(self.config.LogDebugMessages)
        interface.LauncherLogging.setup_logfile(self.config.LogPath)
        
        self.launcherPath = os.getcwd()
        
        if depotdl_path and (path.exists(depotdl_path)) and (path.isfile(depotdl_path)):
            self.depotdl_path = path.abspath(depotdl_path)
            logging.info(f"DepotDownloader path overridden: {self.depotdl_path}")
        else:
            self.depotdl_path = None
        
        # Log some information about loaded paths, configs, etc.
        logging.info(f"Working directory: {self.launcherPath}")
        logging.debug(f"Launcher configuration (including overrides):\n{json.dumps(self.config.to_dict(encode_json=True), indent=4)}")
        
        
        #TODO: Initialize Interface
        #TODO: Initialize Notifications


if __name__ == "__main__":
    # Set terminal window title
    set_window_title(f"{NAME} - Unofficial Astroneer Dedicated Server Launcher for Linux")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=[e.value for e in LauncherCommand], help=HELP_COMMAND)
    parser.add_argument("-c", "--config_path", help="The location of the configuration file (default: %(default)s)", type=str, dest="config_path", default="launcher.toml")
    parser.add_argument("-p", "--astro_path", help="The path of the Astroneer Dedicated Server installation (default: %(default)s)", dest="astro_path", default=None)
    parser.add_argument("-d", "--depotdl_path", help="The path to anm existing depotdownloader executable (default: %(default)s)", dest="depotdl_path", default=None)
        
    args = parser.parse_args()
    
    # Print Banner
    print(BANNER_LOGO, end="")
    print(BANNER_SUBTITLE)
    print("")
    print("Unofficial Astroneer Dedicated Server Launcher for Linux")
    print("")
    
    launcher = AstroTuxLauncher(args.config_path, args.astro_path, args.depotdl_path) 
