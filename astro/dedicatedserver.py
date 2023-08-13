import dataclasses
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config
import uuid
from astro.inimulticonfig import INIMultiConfig
from IPy import IP
import utils.misc as misc
from utils  import requests
import logging
from os import path

def encode_fakefloat(num):
    return f"{str(num)}.000000"

def decode_fakefloat(string):
    return round(float(string))

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
    
    @staticmethod
    def ensure_config(config_path, overwrite_ip=False):
        
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
        ip_valid = requests.valid_ip(config.PublicIP)
        
        if ip_valid and (IP(config.PublicIP).iptype() != "PUBLIC"):
            ip_valid = False
            logging.warn("PublicIP field in Dedicated Server config (AstroServerSettings.ini) contained a private IP")
        
        # If requested or IP is invalid, replace with public IP gotten from online service
        if overwrite_ip or not ip_valid:
            try:
                logging.info("Overwriting PublicIP field in Dedicated Server config")
                config.PublicIP = requests.get_public_ip()
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
    Paths: list = list[str]
    MaxClientRate: int = 1000000
    MaxInternetClientRate: int = 1000000
    
    def collect(self, spreadDict):
        """
            Collects the config values from {spreadDict}
        """
        
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
        """
            Spreads the config values out into a dict representing the structure used by the Engine config
        """
        
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
            
            config = DedicatedServerConfig()
                
        # Write config back to file to add missing entried and remove superflous ones
        # In the case of the file not existing prior, it will be created
        new_ini_config = INIMultiConfig(confDict=config.spread())
        
        new_ini_config.write_file(config_path)
        
        return config
        


class AstroDedicatedServer:
    pass

