import dataclasses
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config, global_config
import uuid
from astro.inimulticonfig import INIMultiConfig
from IPy import IP
from utils import net
import logging
from os import path
from utils.misc import ExcludeIfNone
from astro.rcon import PlayerCategory
import re
from typing import Optional, List
import json

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
                os.makedirs(path.dirname(config_path))
            
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
                os.makedirs(path.dirname(config_path))
            
            config = EngineConfig()
                
        # Write config back to file to add missing entried and remove superflous ones
        # In the case of the file not existing prior, it will be created
        new_ini_config = INIMultiConfig(confDict=config.spread())
        
        new_ini_config.write_file(config_path)
        
        return config


#
#   Dedicated Server related logic
#

class AstroDedicatedServer:
    pass

