import dataclasses
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config, global_config
import uuid
from astro.inimulticonfig import INIMultiConfig
from IPy import IP
from utils import net
import logging
from os import path
import os
from utils.misc import ExcludeIfNone, read_build_version
from astro.rcon import PlayerCategory
import re
from typing import Optional, List
import json
from astro.rcon import AstroRCON, PlayerCategory
from datetime import datetime
import subprocess
import pathvalidate
import time
import astro.playfab as playfab
from utils.interface import EventType, ConsoleParser, ProcessOutputThread, DOTS_SPINNER
import psutil
from enum import Enum
import socket
import traceback
from queue import Queue, Empty
import threading
from alive_progress import alive_bar

LOGGER = logging.getLogger("DedicatedServer")
CMD_LOGGER = logging.getLogger("Command")

#
#   Configuration
#

def encode_fakefloat(num):
    return f"{str(num)}.000000"

def decode_fakefloat(string):
    return round(float(string))

class PlayerProperties:
    """ Class representing a PlayerProperties list entry used in the DS config """
    
    ATTRIBUTES = {
        "PlayerFirstJoinName": str,
        "PlayerCategory": PlayerCategory,
        "PlayerGuid": str,
        "PlayerRecentJoinName": str
    }
    
    def __init__(self, PlayerFirstJoinName="", PlayerCategory=PlayerCategory.UNLISTED, PlayerGuid="", PlayerRecentJoinName=""):
        self.PlayerFirstJoinName = PlayerFirstJoinName
        self.PlayerCategory = PlayerCategory
        self.PlayerGuid = PlayerGuid
        self.PlayerRecentJoinName = PlayerRecentJoinName
    
    def to_string(self):
        """ Return string representation of PlayerProperties Object """
        return f'(PlayerFirstJoinName="{self.PlayerFirstJoinName}",PlayerCategory={self.PlayerCategory.value},PlayerGuid="{self.PlayerGuid}",PlayerRecentJoinName="{self.PlayerRecentJoinName}")'
    
    @staticmethod
    def from_string(string):
        """ Create a PlayerProperties object from string stored in DS config """
        # Find string encased by parenthesies
        match = re.search(r"\((.*)\)", string)
        
        if not match:
            raise ValueError(f"Invalid PlayerProperties string: '{string}'({type(string)})")
        
        # Get content inside of parenthesies and split k-v-pairs into list
        args = match.group(1).split(",")
        
        kwargs = {}
        
        # For each argument, split by = to seperate key from value
        for arg in args:
            arg = arg.split("=", 1)
            
            # If no '=' found, the string is invalid
            if len(arg) != 2:
                raise ValueError("Invalid PlayerProperties string string")
            
            key = arg[0].strip()
            value = arg[1].strip()
            
            # Remove quotes(single and double) from value
            value = re.sub(r"\"(.*?)\"", r"\1", re.sub(r"'(.*?)'", r"\1", value))
            
            # If key is a recognized argument, cast to correct type
            # Ignore keys that are unknown
            if key in PlayerProperties.ATTRIBUTES:
                atype = PlayerProperties.ATTRIBUTES[key]
                
                kwargs[key] = atype(value)
        
        pe = PlayerProperties(**kwargs)
        
        return pe

    # See https://github.com/lidatong/dataclasses-json/issues/122
    @staticmethod
    def list_encoder(pp_list):
        """ Encode list of PlayerProperties objects into string list to be used by dataclass """
        
        # If length of list is one, just encode as string instead of list with single element
        if len(pp_list) == 1:
            return pp_list[0].to_string()
        
        return [pp.to_string() for pp in pp_list]
    
    # See https://github.com/lidatong/dataclasses-json/issues/122
    @staticmethod
    def list_decoder(value):
        """ Decode list of strings into list of PlayerProperties """
        # Directly return value, if already decoded
        if value and isinstance(value[0], PlayerProperties):
            return value
        
        # If only one item is present, value will just be a string, so we only have one item
        if value and isinstance(value, str):
            return [PlayerProperties.from_string(value)]
        
        return [PlayerProperties.from_string(pp_str) for pp_str in value]

# Metadata for PlayerProperties List field
pp_list_field = {
    "dataclasses_json": {
        "encoder": PlayerProperties.list_encoder,
        "decoder": PlayerProperties.list_decoder,
    }
}

@dataclass_json
@dataclass
class DedicatedServerConfig:
    bLoadAutoSave: bool = True
    MaxServerFramerate: int = field(metadata=config(encoder=encode_fakefloat, decoder=decode_fakefloat), default=30)
    MaxServerIdleFramerate: int = field(metadata=config(encoder=encode_fakefloat, decoder=decode_fakefloat), default=3)
    bWaitForPlayersBeforeShutdown: bool = False
    PublicIP: str = ""
    ServerName: str = "Astroneer Dedicated Server"
    MaximumPlayerCount: int = 8
    OwnerName: str = ""
    OwnerGuid: str = ""
    PlayerActivityTimeout: int = 0
    ServerPassword: str = ""
    bDisableServerTravel: bool = False
    DenyUnlistedPlayers: bool = False
    VerbosePlayerProperties: bool = True
    AutoSaveGameInterval: int = 900
    BackupSaveGamesInterval: int = 7200
    ServerGuid: str = uuid.uuid4().hex
    ActiveSaveFileDescriptiveName: str = "SAVE_1"
    ServerAdvertisedName: str = ""
    ConsolePort: int = 1234
    ConsolePassword: str = uuid.uuid4().hex
    HeartbeatInterval: int = 55
    ExitSemaphore: Optional[str] = field(metadata=config(exclude=ExcludeIfNone), default=None)
    PlayerProperties: list[PlayerProperties] = field(default_factory=list, metadata=pp_list_field)
    
    @staticmethod
    def ensure_config(config_path, overwrite_ip=False):
        """
            Reads the dedicated server configuration file at the given config_path, if present, baselines it using dataclass and exports it again.
            If the config file is not present yet, also creates it.
            Also ensures PublicIP setting is set correctly and overwrites it according to {overwrite_ip} and forces some settings to specific values.
        """
        
        config = None
        
        if path.exists(config_path):
            # If config file exists, read it into a config object
            if not path.isfile(config_path):
                raise ValueError("Specified config path doesn't point to a file!")
            
            # Load config from INI file
            ini_dict = INIMultiConfig(filePath=config_path).get_dict()
            
            # If no "launcher" section is present in the file, create it as empty
            if not ("/Script/Astro.AstroServerSettings" in ini_dict):
                ini_dict = {"/Script/Astro.AstroServerSettings": {}}
            
            config = DedicatedServerConfig.from_dict(ini_dict["/Script/Astro.AstroServerSettings"])
            
            # Overwrite some values to ensure specific values
            config.VerbosePlayerProperties = True
            config.HearbeatInterval = 55

        else:
            # If config file is not present, create directories and default config
            if not path.exists(path.dirname(config_path)):
                os.makedirs(path.dirname(config_path), exist_ok=True)
            
            config = DedicatedServerConfig()
        
        # Check Public IP field
        ip_valid = net.valid_ip(config.PublicIP)
        
        if ip_valid and (IP(config.PublicIP).iptype() != "PUBLIC"):
            ip_valid = False
            LOGGER.warning("PublicIP field in Dedicated Server config (AstroServerSettings.ini) contained a private IP")
        
        # If requested or IP is invalid, replace with public IP gotten from online service
        if overwrite_ip or not ip_valid:
            try:
                LOGGER.info("Overwriting PublicIP field in Dedicated Server config...")
                config.PublicIP = net.get_public_ip()
            except Exception as e:
                if ip_valid:
                    LOGGER.warn(f"Could not update PublicIP field: {str(e)}")
                else:
                    LOGGER.error(f"Could not update PublicIP field: {str(e)}")
        
        # Write config back to file to add missing entried and remove superflous ones
        # In the case of the file not existing prior, it will be created
        new_ini_config = INIMultiConfig(confDict={"/Script/Astro.AstroServerSettings": config.to_dict(encode_json=True)})
        
        new_ini_config.write_file(config_path)
        
        return config


@dataclass_json
@dataclass
class EngineConfig:
    Port: int = 7777
    AllowEncryption: bool = False
    Paths: list[str] = field(default_factory=list)
    MaxClientRate: int = 1000000
    MaxInternetClientRate: int = 1000000
    
    def collect(self, spreadDict):
        """ Collects the config values from {spreadDict} """
        try:
            self.Port = int(spreadDict["URL"]["Port"])
        except:
            pass
        
        try:
            self.AllowEncryption = spreadDict["SystemSettings"]["net.AllowEncryption"]
        except:
            pass
        
        try:
            self.Paths = spreadDict["Core.System"]["Paths"]
        except:
            pass
        
        try:
            self.MaxClientRate = int(spreadDict["/Script/OnlineSubsystemUtils.IpNetDriver"]["MaxClientRate"])
        except:
            pass
        
        try:
            self.MaxInternetClientRate = int(spreadDict["/Script/OnlineSubsystemUtils.IpNetDriver"]["MaxInternetClientRate"])
        except:
            pass
    
    def spread(self):
        """ Spreads the config values out into a dict representing the structure used by the Engine config """
        
        new_dict = {}
        
        # Create nested dicts
        new_dict["URL"] = {}
        new_dict["SystemSettings"] = {}
        new_dict["Core.System"] = {}
        new_dict["/Script/OnlineSubsystemUtils.IpNetDriver"] = {}
        
        # Insert values
        new_dict["URL"]["Port"] = str(self.Port)
        new_dict["SystemSettings"]["net.AllowEncryption"] = self.AllowEncryption
        new_dict["Core.System"]["Paths"] = self.Paths
        new_dict["/Script/OnlineSubsystemUtils.IpNetDriver"]["MaxClientRate"] = str(self.MaxClientRate)
        new_dict["/Script/OnlineSubsystemUtils.IpNetDriver"]["MaxInternetClientRate"] = str(self.MaxInternetClientRate)
        
        return new_dict
    
    @staticmethod
    def ensure_config(config_path, disable_encryption=True):
        """
            Reads the engine configuration file at the given config_path, if present, baselines it using dataclass and exports it again.
            If the config file is not present yet, also creates it.
        """
        
        config = None
        
        if path.exists(config_path):
            # If config file exists, read it into a config object
            if not path.isfile(config_path):
                raise ValueError("Specified config path doesn't point to a file!")
            
            # Load config from INI file
            ini_dict = INIMultiConfig(filePath=config_path).get_dict()
            
            config = EngineConfig()
            config.collect(ini_dict)
            
            # Overwrite some values to ensure specific values
            config.AllowEncryption = not disable_encryption

        else:
            # If config file is not present, create directories and default config
            if not path.exists(path.dirname(config_path)):
                os.makedirs(path.dirname(config_path), exist_ok=True)
            
            config = EngineConfig()
                
        # Write config back to file to add missing entried and remove superflous ones
        # In the case of the file not existing prior, it will be created
        new_ini_config = INIMultiConfig(confDict=config.spread())
        
        new_ini_config.write_file(config_path)
        
        return config


#
#   Dedicated Server related logic
#

@dataclass_json
@dataclass
class ServerStatistics:
    """ Stores the current data received from the 'DSServerStatistics' RCON command """
    
    build: str = None
    ownerName: str = None
    maxInGamePlayers: int = None
    playersKnownToGame: int = None
    saveGameName: str = None
    playerActivityTimeout: int = None
    secondsInGame: int = None
    serverName: str = None
    serverURL: str = None
    averageFPS: float = None
    hasServerPassword: bool = None
    isEnforcingWhitelist: bool = None
    creativeMode: bool = None
    isAchievementProgressionDisabled: bool = None

@dataclass
class PlayerInfo:
    playerGuid: str = None
    playerCategory: PlayerCategory = None
    playerName: str = None
    inGame: bool = None
    index: int = None

@dataclass_json
@dataclass
class PlayerList:
    """ Stores the current data received from the 'DSListPlayers' RCON command """
    
    playerInfo: list[PlayerInfo] = field(default_factory=list)


def encoder_datetime_gameinfo(dt):
    return dt.strftime("%Y.%m.%d-%H.%M.%S")

def decoder_datetime_gameinfo(string):
    return datetime.strptime(string, "%Y.%m.%d-%H.%M.%S")

@dataclass
class GameInfo:
    name: str = None
    date: datetime = field(metadata=config(encoder=encoder_datetime_gameinfo, decoder=decoder_datetime_gameinfo), default=None)
    bHasBeenFlaggedAsCreativeModeSave: bool = None

@dataclass_json
@dataclass
class GameList:
    """ Stores the current data received from the 'DSListGames' RCON command """
    
    activeSaveName: str = None
    gameList: list[GameInfo] = field(default_factory=list)

class ServerStatus(Enum):
    OFF = "off"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"

ASTRO_DS_CONFIG_PATH = "Astro/Saved/Config/WindowsServer/"

class AstroDedicatedServer:
    
    def __init__(self, launcher):
        self.launcher = launcher
        
        self.astro_path = self.launcher.config.AstroServerPath
        self.wine_exec = self.launcher.wineexec
        self.wineserver_exec = self.launcher.wineserverexec
        self.wine_pfx = self.launcher.config.WinePrefixPath
        
        # Variables for storing data received from server
        self.curr_server_stat = None
        self.curr_player_list = None
        self.curr_game_list = None
        
        # Stores the time the last status update was performed
        self.last_server_status = None
        
        # Load configuration
        ds_config_path = path.join(self.astro_path, ASTRO_DS_CONFIG_PATH, "AstroServerSettings.ini")
        engine_config_path = path.join(self.astro_path, ASTRO_DS_CONFIG_PATH, "Engine.ini")
        
        self.ds_config = DedicatedServerConfig.ensure_config(ds_config_path, self.launcher.config.OverwritePublicIP)
        self.engine_config = EngineConfig.ensure_config(engine_config_path, self.launcher.config.DisableEncryption)
        
        LOGGER.debug(f"Dedicated Server configuration (including overrides):\n{json.dumps(self.ds_config.to_dict(encode_json=True), indent=4)}")
        LOGGER.debug(f"Engine configuration (including overrides):\n{json.dumps(self.engine_config.to_dict(encode_json=True), indent=4)}")
        
        # Warning, if encryption is enables
        if self.engine_config.AllowEncryption:
            LOGGER.warning("Encryption is enabled. Currently, this doesn't work when running the Astroneer Dedicated Server using WINE")
            LOGGER.warning("Players that have encryption disabled will also ne be able to play on a server having encryption enabled")
        else:
            LOGGER.info("NOTICE: Encryption is disabled. All players that want to join the Dedicated Server have to disable encryption on their clients too")
        
        # RCON
        self.rcon = AstroRCON(self.ds_config.ConsolePort, self.ds_config.ConsolePassword)
        
        # DS Process related
        self.process = None
        self.process_out_queue = Queue()
        self.process_out_thread = None
        
        # XAuth for playfab API
        self.curr_xauth = None
        self.time_last_xauth = None
        
        # Status of the Dedicated Server
        self.status = ServerStatus.OFF
        self.build_version = None
        
        # Information about Playfab registration
        self.registered = False
        self.lobby_id = None
    
    def reload_ds_config(self):
        """ Reads the configuration file for the Dedicated Server again """
        
        ds_config_path = path.join(self.astro_path, ASTRO_DS_CONFIG_PATH, "AstroServerSettings.ini")
        self.ds_config = DedicatedServerConfig.ensure_config(ds_config_path, self.launcher.config.OverwritePublicIP)
    
    def server_loop(self):
        """
            Loop to run while dedicated server is running that receives/sends data, executes commands and more
        """
        
        while True:
            # Exit loop, if server is off
            if self.status == ServerStatus.OFF:
                break
            
            # If RCON is not connected, try to connect
            if not self.rcon.connected:
                conn = self.rcon.ensureConnection()
                
                # After connecting, toggle whiltelist quickly
                if conn:
                    self.quick_toggle_whitelist()
                else:
                    LOGGER.debug("Failed to connect RCON")
            
            # Check server process status
            proc_status = self.process.poll()
            if proc_status is not None:
                if self.status == ServerStatus.STOPPING and proc_status == 0:
                    LOGGER.info("Dedicated Server shut down gracefully")
                    break
                
                if proc_status != 0:
                    self.launcher.notifications.send_event(EventType.CRASH, server_version=self.build_version)
                
                # Server process has exited
                LOGGER.debug(f"Server process closed with exit code {proc_status}")
                break
            else:
                # Print all lines currently in process output queue
                while True:
                    try:
                        line = self.process_out_queue.get_nowait()
                    except Empty:
                        break
                    else:
                        line = line.replace("\n", "")   # Remove newline character, since it it unnecessary
                        LOGGER.debug(f"[AstroDS] {line}")
            
            # If not connected to RCON, skip following code as it requires RCON
            if not self.rcon.connected:
                logging("RCON is not connected, skipping related functionality")
                time.sleep(self.launcher.config.ServerStatusInterval)
                continue
            
            update_server_data = False
            
            if self.last_server_status is None:
                LOGGER.debug("Doing initial Server status data update")
                
                # If we haven't requested any data yet, do it now
                update_server_data = False
                if self.update_server_info():
                    self.last_server_status = time.time()
                else:
                    LOGGER.warning("Getting information from Dedicated Server failed!")
                
            elif (time.time() - self.last_server_status) >= self.launcher.config.ServerStatusInterval:
                # If the time interval since the last status update is big wnough, do another one
                update_server_data = True
            
            # Ensure XAuth is present
            if update_server_data:
                self.get_XAuth()
            
            #TODO: Get info from Playfab API
            
            #
            # Update Server status data and compare to previous data
            # to get joined and left players aswell as savegame changes
            #
            
            if update_server_data and not (self.status == ServerStatus.STOPPING):                
                try:
                    prev_online_players = [pi for pi in self.curr_player_list.playerInfo if pi.inGame]
                    prev_online_player_guids = [pi.playerGuid for pi in prev_online_players]
                    
                    prev_active_save_name = self.curr_game_list.activeSaveName
                    
                    if (prev_active_save_name is not None) and (prev_active_save_name != ""):
                        save_date_list = [gi.date for gi in self.curr_game_list.gameList if gi.name == prev_active_save_name]
                        prev_active_save_time = save_date_list[0] if len(save_date_list) > 0 else 0
                    else:
                        prev_active_save_time = 0
                    
                    if self.update_server_info():
                        self.last_server_status = time.time()
                        
                        online_players = [pi for pi in self.curr_player_list.playerInfo if pi.inGame]
                        online_player_guids = [pi.playerGuid for pi in online_players]
                        
                        # If the amount of players now is greater than before the update, players have joined
                        if len(online_players) > len(prev_online_players):
                            # Get difference of Player GUIDs to find out, who joined
                            player_diff_guid = list(set(online_player_guids) - set(prev_online_player_guids))
                            
                            # Maybe redundant check
                            if len(player_diff_guid) > 0:
                                player_diff = [{"name": pi.playerName, "guid": pi.playerGuid} for pi in self.curr_player_list.playerInfo if pi.playerGuid in player_diff_guid]
                                
                                for info in player_diff:
                                    self.launcher.notifications.send_event(EventType.PLAYER_JOIN, player_name=info["name"], player_guid=info["guid"], server_version=self.build_version)
                                    
                                    #TODO: Maybe set players to pending with command and refresh config file

                        # If the amount of players now is smaller than before the update, players have left
                        if len(prev_online_players) > len(online_players):
                            # Get difference of Player GUIDs to find out, who left
                            player_diff_guid = list(set(prev_online_player_guids) - set(online_player_guids))
                            
                            # Maybe redundant check
                            if len(player_diff_guid) > 0:
                                player_diff = [{"name": pi.playerName, "guid": pi.playerGuid} for pi in self.curr_player_list.playerInfo if pi.playerGuid in player_diff_guid]
                                
                                for info in player_diff:
                                    self.launcher.notifications.send_event(EventType.PLAYER_LEAVE, player_name=info["name"], player_guid=info["guid"], server_version=self.build_version)
                        
                        # Get current savegame information
                        active_save_name = self.curr_game_list.activeSaveName
                        
                        if (active_save_name is not None) and (active_save_name != ""):
                            save_date_list = [gi.date for gi in self.curr_game_list.gameList if gi.name == active_save_name]
                            active_save_time = save_date_list[0] if len(save_date_list) > 0 else 0
                        else:
                            active_save_time = 0
                        
                        # If active save names are different, the server changed savegame
                        if active_save_name != prev_active_save_name:
                            self.launcher.notifications.send_event(EventType.SAVEGAME_CHANGE, savegame_name=active_save_name, server_version=self.build_version)
                        else:
                            # If save was not changed, check if server saved the game
                            if active_save_time != prev_active_save_time:
                                self.launcher.notifications.send_event(EventType.SAVE, savegame_name=active_save_name, server_version=self.build_version)
                except Exception as e:
                    LOGGER.debug(f"Error while doing status update: {str(e)}")
                    LOGGER.error(traceback.format_exc())
            
            
            # Handle console commands in queue
            while not self.launcher.cmd_queue.empty():                
                args = self.launcher.cmd_queue.get()
                
                
                #TODO: Change functions in server such that they return a boolean AND a message, which makes logging easier
                
                
                try:
                    if args["cmd"] == ConsoleParser.Command.SHUTDOWN:
                        success = self.shutdown()
                        
                        if not success:
                            CMD_LOGGER.warning("There was a problem while shutting down the dedicated server")
                        
                    elif args["cmd"] == ConsoleParser.Command.RESTART:
                        #TODO: IMPLEMENT
                        CMD_LOGGER.warning("The restart command is not implemented yet")
                        
                    elif args["cmd"] == ConsoleParser.Command.INFO:
                        if self.curr_server_stat is not None:
                            CMD_LOGGER.info("Information about the Dedicated Server:")
                            CMD_LOGGER.info(f"    - Build: {self.curr_server_stat.build}")
                            CMD_LOGGER.info(f"    - Server URL: {self.curr_server_stat.serverURL}")
                            CMD_LOGGER.info(f"    - Owner: {self.curr_server_stat.ownerName}")
                            CMD_LOGGER.info(f"    - Has Password: {'yes' if self.curr_server_stat.hasServerPassword else 'no'}")
                            CMD_LOGGER.info(f"    - Whitelist: {'enabled' if self.curr_server_stat.isEnforcingWhitelist else 'disabled'}")
                            CMD_LOGGER.info(f"    - Creative Mode: {'yes' if self.curr_server_stat.creativeMode else 'no'}")
                            CMD_LOGGER.info(f"    - Save Game: {self.curr_server_stat.saveGameName}")
                            CMD_LOGGER.info(f"    - Players: {len(self.curr_player_list.playerInfo)}/{self.curr_server_stat.maxInGamePlayers}")
                            CMD_LOGGER.info(f"    - Average FPS: {self.curr_server_stat.averageFPS}")
                        else:
                            CMD_LOGGER.info("Server information not available right now")

                    elif args["cmd"] == ConsoleParser.Command.KICK:
                        self.kick_player(name=args["player"], guid=args["player"])

                    elif args["cmd"] == ConsoleParser.Command.WHITELIST:
                        if args["subcmd"] == ConsoleParser.WhitelistSubcommand.ENABLE:
                            success = self.set_whitelist_enabled(True)
                            
                            if success:
                                CMD_LOGGER.info("Successfully enabled whitelist")
                        elif args["subcmd"] == ConsoleParser.WhitelistSubcommand.DISABLE:
                            success = self.set_whitelist_enabled(False)
                            
                            if success:
                                CMD_LOGGER.info("Successfully disabled whitelist")
                        elif args["subcmd"] == ConsoleParser.WhitelistSubcommand.STATUS:
                            CMD_LOGGER.info(f"The whitelist is currently {'enabled' if self.curr_server_stat.isEnforcingWhitelist else 'disabled'}")
                        
                        if not success:
                            CMD_LOGGER.warning("There was a problem while setting the whitelist status")

                    elif args["cmd"] == ConsoleParser.Command.LIST:
                        if self.curr_player_list is not None:
                            if args["category"] == ConsoleParser.ListCategory.ALL:
                                category = None
                            else:
                                category = PlayerCategory[args["category"].name]
                            
                            CMD_LOGGER.info("Online Players:")
                            
                            for pi in self.curr_player_list.playerInfo:
                                if pi.inGame and ((category is None) or (category == pi.playerCategory)):
                                    CMD_LOGGER.info(f"    - {pi.playerName}({pi.playerGuid})")
                        else:
                            CMD_LOGGER.info("Player information not available right now")

                    elif args["cmd"] == ConsoleParser.Command.SAVEGAME:
                        if args["subcmd"] == ConsoleParser.SaveGameSubcommand.LOAD:
                            try:
                                success = self.load_game(args["save_name"])
                            except Exception as e:
                                CMD_LOGGER.error(f"Error while executing command: {str(e)}")
                            
                            if success:
                                CMD_LOGGER.info(f"Successfully loaded {args['save_name']}")
                            else:
                                CMD_LOGGER.warning("There was a problem while executing the command")
                        if args["subcmd"] == ConsoleParser.SaveGameSubcommand.SAVE:
                            try:
                                success = self.save_game(args["save_name"])
                            except Exception as e:
                                CMD_LOGGER.error(f"Error while executing command: {str(e)}")
                                
                            if success:
                                CMD_LOGGER.info("Successfully saved the game")
                            else:
                                CMD_LOGGER.warning("There was a problem while executing the command")
                        if args["subcmd"] == ConsoleParser.SaveGameSubcommand.NEW:
                            try:
                                success = self.new_game(args["save_name"])
                            except Exception as e:
                                CMD_LOGGER.error(f"Error while executing command: {str(e)}")
                                
                            if success:
                                CMD_LOGGER.info("Successfully created a new save game")
                            else:
                                CMD_LOGGER.warning("There was a problem while executing the command")
                        if args["subcmd"] == ConsoleParser.SaveGameSubcommand.LIST:
                            if self.curr_game_list is not None:
                                
                                CMD_LOGGER.info("Savegames:")
                                
                                for gi in self.curr_game_list.gameList:
                                    CMD_LOGGER.info(f"    - {gi.name} [{gi.date}]  Creative: {gi.bHasBeenFlaggedAsCreativeModeSave}")
                            else:
                                CMD_LOGGER.info("Savegame information not available right now")
                    
                    # Send notification event after executing command
                    self.launcher.notifications.send_event(EventType.COMMAND, command=args["cmdline"], server_version=self.build_version)
                except Exception as e:
                    LOGGER.error(f"Error occured while executing command: {str(e)}")
        
        # Kill remaining wine processes
        self.kill()
    
    # Server process management methods
    
    def start(self):
        """
            Start the dedicated server process and wait for it to be registered to playfab
        """
        
        LOGGER.info("Preparing to start the Dedicated Server...")
        
        ip_port_combo = f"{self.ds_config.PublicIP}:{self.engine_config.Port}"
        
        # Ensure XAuth is present  
        self.get_XAuth()
        
        # Deregister all still with playfab registered servers to avoid issues
        old_lobbyIDs = self.deregister_all_servers()
        
        start_time = time.time()
        try:
            self.start_process()
        except Exception as e:
            LOGGER.error(f"Could not start Dedicated Server process: {str(e)}")
            return False
        
        self.build_version = read_build_version(self.astro_path)
        
        # If process has exited immediately, something went wrong
        if self.process.poll() is not None:
            LOGGER.error("Dedicated Server process died immediately")
            return False
        
        self.status = ServerStatus.STARTING
        
        LOGGER.info(f"Started Dedicated Server process (v{str(self.build_version)}). Waiting for registration...")
        
        wait_time = self.launcher.config.PlayfabAPIInterval
        
        # Wait for DS to finish registration
        with alive_bar(title="Waiting for Dedicated Server to register with Playfab", spinner=DOTS_SPINNER, bar=None, receipt=True, enrich_print=False, monitor=False, stats=False) as bar:
            while not self.registered:
                # Print all lines currently in process output queue
                while True:
                    try:
                        line = self.process_out_queue.get_nowait()
                    except Empty:
                        break
                    else:
                        line = line.replace("\n", "")   # Remove newline character, since it it unnecessary
                        LOGGER.debug(f"[AstroDS] {line}")
                
                # Try to connect to RCON early to support shutdown command
                if not self.rcon.connected:
                    conn = self.rcon.ensureConnection()
                    
                    # After connecting, toggle whiltelist quickly
                    if conn:
                        LOGGER.debug("Connected to RCON")
                        self.quick_toggle_whitelist()
                
                try:
                    # Request registration status
                    response = playfab.get_server(ip_port_combo, self.curr_xauth)
                    
                    # Update progress bar
                    bar()
                    
                    if response["status"] != "OK":
                        continue
                    
                    registered_servers = response["data"]["Games"]
                    
                    lobbyIDs = [srv["LobbyID"] for srv in registered_servers]
                    
                    # If the set of lobbyIDs without the old ones is empty, the server hasn't registered yet
                    if len(set(lobbyIDs) - set(old_lobbyIDs)) == 0:
                        time.sleep(self.launcher.config.PlayfabAPIInterval)
                    else:
                        now = time.time()
                        
                        # Only mark server as registered, if passed time is greater thanb 15 secords (kept from AstroLauncher)
                        if (now - start_time) > 15:
                            self.registered = True
                            self.lobby_id = registered_servers[0]["LobbyID"]
                    
                    proc_code = self.process.poll()
                    if proc_code is not None:
                        if (proc_code == 0) and (self.status == ServerStatus.STOPPING):
                            return False
                        
                        LOGGER.error("Server was forcefully closed before registration")
                        return False
                except:
                    # kept from AstroLauncher
                    LOGGER.debug("Checking for registration failed. Probably rate limit, Backing off and trying again...")
                    
                    # If Playfab API wait time is below 30 seconds, increase it by one
                    if self.launcher.config.PlayfabAPIInterval < 30:
                        self.launcher.config.PlayfabAPIInterval += 1
                    
                    time.sleep(self.launcher.config.PlayfabAPIInterval)
        
        self.launcher.config.PlayfabAPIInterval = wait_time
        
        done_time = time.time()
        elapsed = done_time - start_time
        
        LOGGER.info(f"Dedicated Server ready! Took {round(elapsed, 2)} seconds to register")
        
        self.status = ServerStatus.RUNNING
        
        self.launcher.notifications.send_event(EventType.START, server_version=self.build_version)
        
        return True
    
    def start_process(self):
        """ Start the server process and set the status to RUNNING """
        
        LOGGER.debug("Starting Dedicated Server process...")
        
        cmd = [self.wine_exec, path.join(self.astro_path, "AstroServer.exe"), "-log"]
        env = os.environ.copy()
        env["WINEPREFIX"] = self.wine_pfx
        
        LOGGER.debug(f"Executing command '{' '.join(cmd)}' in WINE prefix '{self.wine_pfx}'...")
        
        self.process = subprocess.Popen(cmd, env=env, cwd=self.astro_path, stderr=subprocess.PIPE, bufsize=1, close_fds=True, text=True)
        
        self.process_out_thread = ProcessOutputThread(self.process.stderr, self.process_out_queue)
        self.process_out_thread.start()
        
        time.sleep(0.01)
    
    def kill(self):
        """ Kill the Dedicated Server process using wineserver -k """
        
        # Stop reading thread
        if self.process_out_thread:
            self.process_out_thread.stop()
        
        cmd = [self.wineserver_exec, "-k", "-w"]
        env = os.environ.copy()
        env["WINEPREFIX"] = self.wine_pfx
        
        LOGGER.debug(f"Executing command '{' '.join(cmd)}' in WINE prefix '{self.wine_pfx}'...")
        
        process = subprocess.Popen(cmd, env=env)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            LOGGER.warning("Server took longer than 15 seconds to kill, killing wineserver")
            process.kill()
        
        self.status = ServerStatus.OFF
    
    # Server interaction methods (RCON)
    
    def get_player_info(self, name=None, guid=None):
        """ Get the PlayerInfo object related to the player whose name or GUID match """
        
        if (name is None) and (guid is None):
            raise ValueError("One of name, guid has to be provided")
        
        if not self.curr_player_list:
            return None
        
        for player_info in self.curr_player_list.playerInfo:
            if ((name and player_info.playerName == name)
                or (guid and player_info.playerGuid == guid)):
                return player_info
    
    def shutdown(self):
        """
            Shut down the dedicated server by sending it the DSServerShutdown command.
            Also clears the current server information and sets the status to STOPPING.
        """
        
        if not self.rcon.connected:
            return False
        
        self.launcher.notifications.send_event(EventType.SHUTDOWN, server_version=self.build_version)
        
        res = self.rcon.DSServerShutdown()
        
        if res == True:
            self.curr_server_stat = None
            self.curr_player_list = None
            self.curr_game_list = None
        
            self.status = ServerStatus.STOPPING
        
            return True
        else:
            return False

    def set_player_category(self, category, name=None, guid=None, force=False):
        """
            Sets the category of the player identified by either the name or guid.
            
            Arguments:
                - category: A rcon.PlayerCategory to set
                - name/guid: Name/GUID to identify the Player
                - force: Wether to send the command without checking the player list first.
                    Only works, if {name} is set

            Returns: A boolean indicating the success
        """
        
        if (name is None) and (guid is None):
            raise ValueError("One of name, guid has to be provided")
        
        if not self.rcon.connected or (self.status != ServerStatus.RUNNING):
            return False
        
        if force:
            if name is None:
                raise ValueError("force=True can only be used if a name is given")
            
            res = self.rcon.DSSetPlayerCategoryForPlayerName(name, category)
        else:
            player_info = self.get_player_info(name=name, guid=guid)
            
            if player_info is None:
                return False
            
            res = self.rcon.DSSetPlayerCategoryForPlayerName(player_info.playerName, category)
        
        if not isinstance(res, dict):
            return False
        
        return res["status"]
    
    def set_whitelist_enabled(self, enabled=True):
        """
            Changes the enables state of the Whitelist
            
            Arguments:
                - enabled: Wether to enable/disable the whitelist
            
            Returns: A boolean indicating the success
        """
        
        if not self.rcon.connected or (self.status != ServerStatus.RUNNING):
            return False
        
        if self.curr_server_stat and (self.curr_server_stat.isEnforcingWhitelist == enabled):
            return True
        
        res = self.rcon.DSSetDenyUnlisted(enabled)
        
        if not isinstance(res, bytes):
            return False
        
        res = res.decode()
        if res[:67] == "UAstroServerCommExecutor::DSSetDenyUnlisted: SetDenyUnlistedPlayers" and res[-1:] == "1":
            self.curr_server_stat.isEnforcingWhitelist = enabled
            return True
        else:
            return False
    
    def kick_player(self, guid=None, name=None, force=False):
        """
            Kicks the player identified by name/guid.
            
            Arguments:
                - name/guid: Name/GUID to identify the Player
                - force: Wether to send the command without checking the player list first.
                    Only works, if {guid} is set
            
            Returns: A boolean indicating the success
        """
        
        if (name is None) and (guid is None):
            raise ValueError("One of name, guid has to be provided")
        
        if not self.rcon.connected or (self.status != ServerStatus.RUNNING):
            return False
        
        if force:
            if guid is None:
                raise ValueError("force=True can only be used if a guid is given")
            
            res = self.rcon.DSKickPlayerGuid(guid)
        else:
            player_info = self.get_player_info(name=name, guid=guid)
            
            if player_info is None:
                LOGGER.warning("Unknown Player")
                return False
            
            res = self.rcon.DSKickPlayerGuid(player_info.playerGuid)
        
        if not isinstance(res, bytes):
            LOGGER.warning("Error while executing command")
            return False
        
        res = res.decode()
        success = res[:42] == "UAstroServerCommExecutor::DSKickPlayerGuid" and res[-1:] == "d"
        
        if success:
            if force:
                LOGGER.info(f"Kicked Player with GUID '{guid}'")
            else:
                LOGGER.info(f"Kicked Player '{player_info.playerName}'")
                
            return True
        else:
            return success
    
    def update_server_info(self):
        """
            Updates the stored information about the dedicated server
            
            Returns: A boolean indicating the success
        """
        
        if not self.rcon.connected or (self.status != ServerStatus.RUNNING):
            return False
        
        res = self.rcon.DSServerStatistics()
        
        if not isinstance(res, dict):
            return False
        
        self.curr_server_stat = ServerStatistics.from_dict(res)
        
        res = self.rcon.DSListPlayers()
        
        if not isinstance(res, dict):
            return False
        
        self.curr_player_list = PlayerList.from_dict(res)
        
        res = self.rcon.DSListGames()
        
        if not isinstance(res, dict):
            return False
        
        self.curr_game_list = GameList.from_dict(res)
        
        return True
    
    def save_game(self, name=None):
        """
            Saves the game instantly.
            
            Arguments:
                - [name]: Filename to save the current savegame as
            
            Returns: A boolean indicating the success
        """
        
        if not self.rcon.connected or (self.status != ServerStatus.RUNNING):
            return False
        
        res = self.rcon.DSSaveGame(name)
        
        return res == True
    
    def load_game(self, save_name, force=False):
        """
            Loads the savegame specified in {save_game}.
            
            Arguments:
                - save_name: Name of the savegame to load
                - [force]: Wether to send the command without checking the current saves list first
            
            Returns: A boolean indicating the success
        """
        
        if not self.rcon.connected or (self.status != ServerStatus.RUNNING):
            return False
        
        # If force is false, check that {save_name} is actually in the save game list
        if not force:
            if self.curr_game_list is None:
                raise TypeError("The current game list is None")
            
            found = False
            
            for game in self.curr_game_list.gameList:
                if game.name == save_name:
                    found = True
            
            if not found:
                return False
        
        if not pathvalidate.is_valid_filename(save_name):
            raise ValueError(f"'{save_name}' is not a valid savegame name")
        
        res = self.rcon.DSLoadGame(save_name)
        
        if not res:
            return False
        
        # Wait until the save is loaded (is the active save)
        active_save_name = None
        
        tries = 0   # Maximum of 15 tries
        
        while (active_save_name != save_name) and (tries < 15):
            res = self.rcon.DSListGames()
            
            if not isinstance(res, dict):
                return False
            
            active_save_name = res["activeSaveName"]
            tries += 1
            time.sleep(0.01)
        
        return True
    
    def new_game(self, name=None):
        """
            Starts a new savegame.
            
            WARNING: Currently crashes the server running under wine
            
            Returns: A boolean indicating the success
        """
        
        # Prevent people from using this
        LOGGER.warning("Starting a new save game has been disabled currently due to the dedicated server crashing under wine while performing the operation")
        LOGGER.warning("Please create new save games from inside the game")
        return False
        
        if not self.rcon.connected or (self.status != ServerStatus.RUNNING):
            return False
        
        res1 = self.rcon.DSNewGame(name)
        res2 = self.rcon.DSSaveGame(name)
        
        return (res1 == True) and (res2 == True)
    
    # Utility functions
    
    def quick_toggle_whitelist(self):
        """
            Quickly toggle the whitelist status two times, which forces the server to put every player who hast joined the current save into the INI file
        """
        
        if not self.rcon.connected or (self.status != ServerStatus.RUNNING):
            return False
        
        if not self.curr_server_stat:
            return False
        
        wl_status = self.curr_server_stat.isEnforcingWhitelist
        
        self.set_whitelist_enabled(not wl_status)
        self.set_whitelist_enabled(wl_status)
        self.reload_ds_config()
        
        return True
    
    def get_XAuth(self):
        # If no XAuth has been requested yet, or the last one is over an hour old, try to get new XAuth
        if (self.time_last_xauth is None) or ((datetime.now() - self.time_last_xauth).total_seconds() > 3600):
            XAuth = None
            tries = 5
            
            # While getting XAuth wasn't successful, retry
            while XAuth is None:
                if tries <= 0:
                    LOGGER.error("Unable to get XAuth token after aeveral tries.  Are you connected to the internet?")
                    raise TimeoutError("Gave up after several tries while generating XAuth token")
                
                try:
                    LOGGER.debug("Generating new XAuth...")
                    XAuth = playfab.generate_XAuth(self.ds_config.ServerGuid)
                except Exception as e:
                    LOGGER.debug("Error while generating XAuth: " + str(e))
                    
                    # If not successful, wait 10 seconds
                    time.sleep(10)
            
            self.curr_xauth = XAuth
            self.time_last_xauth = datetime.now()
    
    def deregister_all_servers(self):
        """
            Tries to deregister all servers registered with Playfab with matching IP-Port-combination.
            
            Returns: List of LobbyIDs of deregistered servers
        """
        
        if not self.curr_xauth:
            raise ValueError("Not XAuth present, can't use Playfab API")
        
        # Combination of PublicIP and Port is used as game ID, so we need to get it
        ip_port_combo = f"{self.ds_config.PublicIP}:{self.engine_config.Port}"
        
        # Get registered servers from Playfab API
        response = playfab.get_server(ip_port_combo, self.curr_xauth)
        
        # If API set status to anything other than OK, we can't continue and simply return
        if response["status"] != "OK":
            raise playfab.APIError("API responded with non-OK status")
        
        registered_servers = response["data"]["Games"]
        
        if len(registered_servers) > 0:
            LOGGER.debug(f"Trying to deregister {len(registered_servers)} servers with maching IP-Port-combination from Playfab...")
            
            for i, srv in enumerate(registered_servers):
                LOGGER.debug(f"Deregistering server {i} with LobbyID {srv['LobbyID']}...")
                
                response = playfab.deregister_server(srv["LobbyID"], self.curr_xauth)
                
                if ("status" in response) and (response["status"] != "OK"):
                    LOGGER.warning(f"Problems while deregistering server {i}. It may still be registered!")
            
            LOGGER.debug("Finished deregistration")
            
            # AstroLauncher has this for some reason, so keep it for now
            time.sleep(1)
            
            return [srv["LobbyID"] for srv in registered_servers]
        
        return []
    
    def check_ports_free(self):
        
        def is_port_in_use(port, tcp=True):
            """ Checks if port is in use for TCP if {tcp} is true and for UDP if {tcp} is false """
            conns = psutil.net_connections("inet")
            matching = [c for c in conns 
                        if c.type == (socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM)
                        and c.laddr[1] == port]
            
            return len(matching) > 0
        
        sp_free = not is_port_in_use(self.engine_config.Port)
        cp_free = not is_port_in_use(self.ds_config.ConsolePort)
        
        if not sp_free:
            LOGGER.error(f"Server Port ({self.engine_config.Port}) already in use by different process")
            return False
        
        if not cp_free:
            LOGGER.error(f"Console Port ({self.ds_config.ConsolePort}) already in use by different process")
            return False
        
        return True