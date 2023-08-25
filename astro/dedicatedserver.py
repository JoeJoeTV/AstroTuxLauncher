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
from utils.misc import ExcludeIfNone
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
from utils.interface import EventType, ConsoleParser

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
            raise ValueError("Invalid PlayerProperties string string")
        
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
        return [pp.to_string() for pp in pp_list]
    
    # See https://github.com/lidatong/dataclasses-json/issues/122
    @staticmethod
    def list_decoder(value):
        """ Decode list of strings into list of PlayerProperties """
        # Directly return value, if already decoded
        if value and isinstance(value[0], PlayerProperties):
            return value
        
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
            logging.warn("PublicIP field in Dedicated Server config (AstroServerSettings.ini) contained a private IP")
        
        # If requested or IP is invalid, replace with public IP gotten from online service
        if overwrite_ip or not ip_valid:
            try:
                logging.info("Overwriting PublicIP field in Dedicated Server config")
                config.PublicIP = net.get_public_ip()
            except:
                if ip_valid:
                    logging.warn("Could not update PublicIP field")
                else:
                    logging.error("Could not update PublicIP field")
        
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
    OFF: "off"
    STARTING: "starting"
    RUNNING: "running"
    STOPPING: "stopping"

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
        
        # Load configuration
        ds_config_path = path.join(self.astro_path, ASTRO_DS_CONFIG_PATH, "AstroServerSettings.ini")
        engine_config_path = path.join(self.astro_path, ASTRO_DS_CONFIG_PATH, "Engine.ini")
        
        self.ds_config = DedicatedServerConfig.ensure_config(ds_config_path, self.launcher.config.OverwritePublicIP)
        self.engine_config = EngineConfig.ensure_config(engine_config_path, self.launcher.config.DisableEncryption)
        
        # RCON
        self.rcon = AstroRCON(self.ds_config.ConsolePort, self.ds_config.ConsolePassword)
        self.process = None
        
        # XAuth for playfab API
        self.curr_xauth = None
        self.time_last_xauth = None
        
        # Status of the Dedicated Server
        self.status = ServerStatus.OFF
        
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
                    logging.debug("Failed to connect RCON")
            
            # Check server process status
            proc_status = self.process.poll()
            if proc_status is not None:
                if self.status == ServerStatus.STOPPING and proc_status == 0:
                    logging.info("Dedicated Server shut down gracefully")
                    break
                
                # Server process has exited
                logging.debug(f"Server process closed with exit code {proc_status}")
                break
            
            # Ensure XAuth is present
            self.get_XAuth()
            
            #TODO: Get info from Playfab API
            
            # Save player list before updating
            prev_online_players = [pi for pi in self.curr_player_list.playerInfo if pi.inGame]
            prev_online_player_guids = [pi.playerGuid for pi in prev_online_players]
            
            prev_active_save_name = self.curr_game_list.activeSaveName
            if (prev_active_save_name is not None) and (prev_active_save_name != ""):
                prev_active_save_time = [gi.date for gi in self.curr_game_list.gameList if gi.name == prev_active_save_name][0]
            else:
                prev_active_save_time = 0
            
            logging.debug(f"Prev Active SaveGame Name: {prev_active_save_name}")
            logging.debug(f"Prev Active SaveGame Time: {prev_active_save_time}")
            
            # Get information from server via RCON
            if self.rcon.connected and self.update_server_info():
                # Current player list
                online_players = [pi for pi in self.curr_player_list.playerInfo if pi.inGame]
                online_player_guids = [pi.playerGuid for pi in online_players]
                
                # If the amount of players now is greater than before the update, players have joined
                if len(online_players) > len(prev_online_players):
                    # Get difference of Player GUIDs to find out, who joined
                    player_diff_guid = list(set(online_player_guids) - set(prev_online_player_guids))
                    
                    logging.debug(f"Joined GUIDs: {player_diff_guid}")
                    
                    # Maybe redundant check
                    if len(player_diff) > 0:
                        player_diff = [{"name": pi.playerName, "guid": pi.playerGuid} for pi in self.curr_player_list.playerInfo if pi.playerGuid in player_diff_guid]
                        
                        logging.debug(f"Joined Infos: {player_diff}")
                        
                        for info in player_diff:
                            self.launcher.notifications.send_event(EventType.PLAYER_JOIN, player_name=info["name"], player_guid=info["guid"])
                            
                            #TODO: Maybe set players to pending with command and refresh config file
                
                # If the amount of players now is smaller than before the update, players have left
                if len(prev_online_players) > len(online_players):
                    # Get difference of Player GUIDs to find out, who left
                    player_diff_guid = list(set(prev_online_player_guids) - set(online_player_guids))
                    
                    logging.debug(f"Left GUIDs: {player_diff_guid}")
                    
                    # Maybe redundant check
                    if len(player_diff) > 0:
                        player_diff = [{"name": pi.playerName, "guid": pi.playerGuid} for pi in self.curr_player_list.playerInfo if pi.playerGuid in player_diff_guid]
                        
                        logging.debug(f"Left Infos: {player_diff}")
                        
                        for info in player_diff:
                            self.launcher.notifications.send_event(EventType.PLAYER_LEAVE, player_name=info["name"], player_guid=info["guid"])
                
                # Get current savegame information
                active_save_name = self.curr_game_list.activeSaveName
                if (active_save_name is not None) and (active_save_name != ""):
                    active_save_time = [gi.date for gi in self.curr_game_list.gameList if gi.name == active_save_name][0]
                else:
                    active_save_time = 0
                
                logging.debug(f"Active SaveGame Name: {active_save_name}")
                logging.debug(f"Active SaveGame Time: {active_save_time}")
                
                # If active save names are different, the server changed savegame
                if active_save_name != prev_active_save_name:
                    self.launcher.notifications.send_event(EventType.SAVEGAME_CHANGE, savegame_name=active_save_name)
                else:
                    # If save was not changed, check if server saved the game
                    if active_save_time != prev_active_save_time:
                        self.launcher.send_event(EventType.SAVE, savegame_name=active_save_name)
            
            # Handle console commands
            while not self.launcher.cmd_queue.empty():
                # break out of loop, if RCON not available
                if not self.rcon.connected:
                    logging.debug("Can't execute command, because RCON is not connected")
                    break
                
                args = self.launcher.cmd_queue.get()
                
                self.launcher.notifications.send_event(EventType.COMMAND, command=args["cmdline"])
                
                
                #TODO: Change functions in server such that they return a boolean AND a message, which makes logging easier
                
                
                try:
                    if args["cmd"] == ConsoleParser.Command.SHUTDOWN:
                        success = self.shutdown()
                        
                        if not success:
                            logging.warning("There was a problem while shutting down the dedicated server")
                        
                    elif args["cmd"] == ConsoleParser.Command.RESTART:
                        #TODO: IMPLEMENT
                        logging.warning("The restart command is not implemented yet")
                        
                    elif args["cmd"] == ConsoleParser.Command.INFO:
                        if self.curr_server_stat is not None:
                            logging.info("Information about the Dedicated Server:")
                            logging.info(f"    - Build: {self.curr_server_stat.build}")
                            logging.info(f"    - Server URL: {self.curr_server_stat.serverURL}")
                            logging.info(f"    - Owner: {self.curr_server_stat.ownerName}")
                            logging.info(f"    - Has Password: {'yes' if self.curr_server_stat.hasServerPassword else 'no'}")
                            logging.info(f"    - Whitelist: {'enabled' if self.curr_server_stat.isEnforcingWhitelist else 'disabled'}")
                            logging.info(f"    - Creative Mode: {'yes' if self.curr_server_stat.creativeMode else 'no'}")
                            logging.info(f"    - Save Game: {self.curr_server_stat.saveGameName}")
                            logging.info(f"    - Players: {len(self.curr_player_list.playerInfo)}/{self.curr_server_stat.maxInGamePlayers}")
                            logging.info(f"    - Average FPS: {self.curr_server_stat.averageFPS}")
                        else:
                            logging.info("Server information not available right now")

                    elif args["cmd"] == ConsoleParser.Command.KICK:
                        self.kick_player(name=args["player"], guid=args["player"])

                    elif args["cmd"] == ConsoleParser.Command.WHITELIST:
                        if args["subcmd"] == ConsoleParser.WhitelistSubcommand.ENABLE:
                            success = self.set_whitelist_enabled(True)
                            
                            if success:
                                logging.info("Successfully enabled whitelist")
                        elif args["subcmd"] == ConsoleParser.WhitelistSubcommand.DISABLE:
                            success = self.set_whitelist_enabled(False)
                            
                            if success:
                                logging.info("Successfully disabled whitelist")
                        elif args["subcmd"] == ConsoleParser.WhitelistSubcommand.STATUS:
                            logging.info(f"The whitelist is currently {'enabled' if self.curr_server_stat.isEnforcingWhitelist else 'disabled'}")
                        
                        if not success:
                            logging.warning("There was a problem while setting the whitelist status")

                    elif args["cmd"] == ConsoleParser.Command.LIST:
                        if self.curr_player_list is not None:
                            if args["category"] == ConsoleParser.ListCategory.ALL:
                                category = None
                            else:
                                category = PlayerCategory[args["category"].name]
                            
                            logging.info("Online Players:")
                            
                            for pi in self.curr_player_list.playerInfo:
                                if pi.inGame and ((category is None) or (category == pi.playerCategory)):
                                    logging.info(f"    - {pi.playerName}({pi.playerGuid})")
                        else:
                            logging.info("Player information not available right now")

                    elif args["cmd"] == ConsoleParser.Command.SAVEGAME:
                        if args["subcmd"] == ConsoleParser.SaveGameSubcommand.LOAD:
                            try:
                                success = self.load_game(args["save_name"])
                            except Exception as e:
                                logging.error(f"Error while executing command: {str(e)}")
                            
                            if success:
                                logging.info(f"Successfully loaded {args['save_name']}")
                            else:
                                logging.warning("There was a problem while executing the command")
                        if args["subcmd"] == ConsoleParser.SaveGameSubcommand.SAVE:
                            try:
                                success = self.save_game(args["save_name"])
                            except Exception as e:
                                logging.error(f"Error while executing command: {str(e)}")
                                
                            if success:
                                logging.info("Successfully saved the game")
                            else:
                                logging.warning("There was a problem while executing the command")
                        if args["subcmd"] == ConsoleParser.SaveGameSubcommand.NEW:
                            try:
                                success = self.new_game(args["save_name"])
                            except Exception as e:
                                logging.error(f"Error while executing command: {str(e)}")
                                
                            if success:
                                logging.info("Successfully created a new save game")
                            else:
                                logging.warning("There was a problem while executing the command")
                        if args["subcmd"] == ConsoleParser.SaveGameSubcommand.LIST:
                            if self.curr_game_list is not None:
                                
                                logging.info("Savegames:")
                                
                                for gi in self.curr_game_list.gameList:
                                    logging.info(f"    - {gi.name} [{gi.data}]  Creative: {gi.bHasBeenFlaggedAsCreativeModeSave}")
                            else:
                                logging.info("Savegame information not available right now")
                except Exception as e:
                    logging.error(f"Error occured while executing command: {str(e)}")
            
            time.sleep(self.launcher.config.ServerStatusInterval)
    
    # Server process management methods
    
    def start(self):
        """
            Start the dedicated server process and wait for it to be registered to playfab
        """
        
        #TODO: Check in launcher calling this function for exception and exit
        
        ip_port_combo = f"{self.ds_config.PublicIP}:{self.engine_config.Port}"
        
        # Ensure XAuth is present  
        self.get_XAuth()
        
        # Deregister all still with playfab registered servers to avoid issues
        old_lobbyIDs = self.deregister_all_servers()
        
        logging.debug("Starting Server process...")
        start_time = time.time()
        try:
            self.start_process()
        except:
            logging.error("Could not start Dedicated Server process")
            return False
        
        # If process has exited immediately, something went wrong
        if self.process.poll() is not None:
            logging.error("Dedicated Server process died immediately")
            return False
        
        self.status = ServerStatus.STARTING
        
        logging.debug("Started Dedicated Server process. Waiting for registration...")
        
        wait_time = self.launcher.config.PlayfabAPIInterval
        
        # Wait for DS to finish registration
        while not self.registered:
            try:
                response = playfab.get_server(ip_port_combo, self.curr_xauth)
                
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
                
                if self.process.poll() is not None:
                    logging.error("Server was closed before registration")
                    return False
            except:
                # kept from AstroLauncher
                logging.debug("Checking for registration failed. Probably radte limit, Backing off and trying again...")
                
                # If Playfab API wait time is below 30 seconds, increase it by one
                if self.launcher.config.PlayfabAPIInterval < 30:
                    self.launcher.config.PlayfabAPIInterval += 1
                
                time.sleep(self.launcher.config.PlayfabAPIInterval)
        
        self.launcher.config.PlayfabAPIInterval = wait_time
        
        done_time = time.time()
        elapsed = start_time - wait_time
        
        logging.info(f"Dedicated Server ready! Took {round(elapsed, 2)} seconds to register")
        
        self.status = ServerStatus.RUNNING
        
        self.launcher.notifications.send_event(EventType.START)
        
        return True
    
    def start_process(self):
        """ Start the server process and set the status to RUNNING """
        
        logging.debug("Starting Dedicated Server process...")
        
        cmd = [self.wine_exec, path.join(self.astro_path, "AstroServer.exe"), "-log"]
        env = os.environ.copy()
        env["WINEPREFIX"] = self.wine_pfx
        
        self.process = subprocess.Popen(cmd, env=env, cwd=self.astro_path)
        time.sleep(0.01)
    
    def kill(self):
        """ Kill the Dedicated Server process using wineserver -k """
        
        cmd = [self.wineserver_exec, "-k", "-w"]
        env = os.environ.copy()
        env["WINEPREFIX"] = self.wine_pfx
        
        process = subprocess.Popen(cmd, env=env)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            logging.warning("Server took longer than 15 seconds to kill, killing wineserver")
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
        
        if not self.rcon.connected or (self.status != ServerStatus.RUNNING):
            return False
        
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
                logging.warning("Unknown Player")
                return False
            
            res = self.rcon.DSKickPlayerGuid(player_info.playerGuid)
        
        if not isinstance(res, bytes):
            logging.warning("Error while executing command")
            return False
        
        res = res.decode()
        success = res[:42] == "UAstroServerCommExecutor::DSKickPlayerGuid" and res[-1:] == "d"
        
        if success:
            if force:
                logging.info(f"Kicked Player with GUID '{guid}'")
            else:
                logging.info(f"Kicked Player '{player_info.playerName}'")
                
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
    
    def new_game(self):
        """
            Starts a new savegame.
            
            WARNING: Currently crashes the server running under wine
            
            Returns: A boolean indicating the success
        """
        
        # Prevent people from using this
        logging.warning("Starting a new save game has been disabled currently due to the dedicated server crashing under wine while performing the operation")
        logging.warning("Please create new games from inside the game")
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
                    logging.error("Unable to get XAuth token after aeveral tries.  Are you connected to the internet?")
                    raise TimeoutError("Gave up after several tries while generating XAuth token")
                
                try:
                    logging.debug("Generating new XAuth...")
                    XAuth = playfab.generate_XAuth(self.ds_config.ServerGuid)
                except Exception as e:
                    logging.debug("Error while generating XAuth: " + str(e))
                    
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
            logging.debug(f"Trying to deregister {len(registered_servers)} servers with maching IP-Port-combination from Playfab...")
            
            for i, srv in enumerate(registered_servers):
                logging.debug(f"Deregistering server {i}")
                
                response = playfab.deregister_server(srv["LobbyID"], self.curr_xauth)
                
                if ("status" in response) and (response["status"] != "OK"):
                    logging.warning(f"Problems while deregistering server {i}. It may still be registered!")
            
            logging.debug("Finished deregistration")
            
            # AstroLauncher has this for some reason
            time.sleep(1)
            
            return [srv["LobbyID"] for srv in registered_servers]
        
        return []