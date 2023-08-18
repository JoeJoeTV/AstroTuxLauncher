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
        
        # Status of the Dedicated Server
        self.status = ServerStatus.OFF
    
    # Server process management methods
    
    def start(self):
        """ Start the server process and set the status to RUNNING """
        
        cmd = [self.wine_exec, path.join(self.astro_path, "AstroServer.exe"), "-log"]
        env = os.environ.copy()
        env["WINEPREFIX"] = self.wine_pfx
        
        self.process = subprocess.Popen(cmd, env=env, cwd=self.astro_path)
        self.status = ServerStatus.STARTING
    
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
        return res[:67] == "UAstroServerCommExecutor::DSSetDenyUnlisted: SetDenyUnlistedPlayers" and res[-1:] == "1"
    
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
                return False
            
            res = self.rcon.DSKickPlayerGuid(player_info.playerGuid)
        
        if not isinstance(res, bytes):
            return False
        
        res = res.decode()
        return res[:42] == "UAstroServerCommExecutor::DSKickPlayerGuid" and res[-1:] == "d"
    
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
        logging.warning("Starting a new save game has been disables currently due to the dedicated server crashing under wine while performing the operation")
        logging.warning("Please create new games from inside the game")
        return False
        
        if not self.rcon.connected or (self.status != ServerStatus.RUNNING):
            return False
        
        res1 = self.rcon.DSNewGame(name)
        res2 = self.rcon.DSSaveGame(name)
        
        return (res1 == True) && (res2 == True)