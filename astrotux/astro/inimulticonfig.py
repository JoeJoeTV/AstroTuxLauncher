#
# File: astro/inimulticonfig.py
# Description: Fuctionality for reading/writing the ini files that the Astroneer Dedicated Server uses
# Note: This file is based upon code from [AstroLauncher](https://github.com/ricky-davis/AstroLauncher)
#

import json
import os.path as path
import os
import chardet

class INIMultiConfig():
    """
        Class representing an INI file with the ability for duplicate keys
    """
    
    # Possible boolean values in the INI file and their meaning as a python boolean value
    BOOLEAN_STATES = {
        "yes"   : True,
        "true"  : True,
        "on"    : True,
        "no"    : False,
        "false" : False,
        "off"   : False
    }
    
    def __init__(self, config_dict: dict = None, file_path: str = None):
        """
            Create new config object. If {file_path} is specified, load config from specified .ini file.
            Else, if {config_dict} is specified, load config from passed dictionary.
            If none is specified, create empty config object
        """
        
        self._dict = {}
        
        if not (file_path is None):
            self.read_file(file_path)
        elif not (config_dict is None) and isinstance(config_dict, dict):
            self.read_dict(config_dict)
    
    def __getitem__(self, key):
        """ Is used, such that values can be accessed like in a dictionary """
        return self._dict[key]
    
    def set_value(self, section: str, key: str, value, append: bool = False) -> None:
        """
            If {append} is False, simpy sets the value of {key} in {section} to {value}.
            If {append} is True, adds value as an additional value with the same key {key} in {section}.
        """
        
        # If section or key is not a string, do nothing
        if (not isinstance(section, str)) or (not isinstance(key, str)):
            return
        
        if append:
            if isinstance(self._dict[section][key], list):
                self._dict[section][key].append(value)
            else:
                self._dict[section][key] = [self._dict[section][key], value]
        else:
            self._dict[section][key] = value
        
    def get_dict(self) -> dict:
        """ Returns the dictionary containing the data of the config """
        return self._dict.copy()
    
    def sections(self) -> set:
        """ Returns a set representing the sections currently present in the config """
        return self._dict.keys()
    
    def read_dict(self, config_dict: dict) -> None:
        """ Reads the given dictionary {config_dict} as config data """
        
        # If {config_dict} is not a dictionary, do nothing
        if not isinstance(config_dict, dict):
            return
        
        # If any section name doesn't reference a dictionary, return
        for _, section in config_dict.items():
            if not isinstance(section, dict):
                return

        self._dict = json.loads(json.dumps(config_dict), parse_int=str, parse_float=str)
    
    def read_file(self, config_path: str) -> None:
        """
            Reads the specified INI file
            
            Arguments:
                - config_path: Path to the .ini file
        """
        
        encoding = INIMultiConfig.get_encoding(config_path)
        
        with open(config_path, "r", encoding=encoding) as cf:
            lines = [line.strip() for line in cf.read().split("\n")]
            
            # Note: The "Global" section will be ignored
            current_section = None
            
            while len(lines) > 0:
                # Get first line and split by separator
                line = lines.pop(0).split("=", 1)
                
                # If we only have one element after split that is surrounded by square brackets, it's a section header
                if (len(line) == 1) and (len(line[0]) >= 2) and (line[0][0] == "[") and (line[0][-1] == "]"):
                    # We have a section header
                    
                    # New section header
                    new_section = line[0][1:-1].strip()
                    
                    # Only set new section, if length of header
                    if (len(new_section) > 0):
                        current_section = new_section
                        self._dict[current_section] = {}
                    
                elif (len(line) > 1):
                    # We have a property
                    
                    # If we're not in a named section, ignore value
                    if (current_section is None):
                        continue
                    
                    key = line[0].strip()
                    value = line[1].strip()
                    
                    # If the value looks like a boolean, convert it using mapping table
                    if value.lower() in INIMultiConfig.BOOLEAN_STATES:
                        value = INIMultiConfig.BOOLEAN_STATES[value.lower()]
                    
                    if not (key in self._dict[current_section]):
                        # If the key does not already exist, create it and assign the value
                        
                        self._dict[current_section][key] = value
                    else:
                        if isinstance(self._dict[current_section][key], list):
                            # If the key already exists and is a list, add the value to the list
                            
                            self._dict[current_section][key].append(value)
                        else:
                            # If the key already exists and is NOT a list, create a new list and add it to the list
                            
                            self._dict[current_section][key] = [self._dict[current_section][key], value]
    
    def write_file(self, config_path: str):
        """
            Writes the configuration to the specified file
            
            Arguments:
                - config_path: Path where the config file should be written
                - overwrite: Wether an error should be thrown, if the file already esists(False) or not(True)
        """
        
        encoding = INIMultiConfig.get_encoding(config_path)
        
        with open(config_path, "w", encoding=encoding) as cf:
            for section in self._dict.keys():
                # Write section header to file
                cf.write(f"[{section}]\n")
                
                properties = self._dict[section]
                
                # Write one line for each key or multiple for multi-values keys
                for key, value in properties.items():
                    if isinstance(value, list):
                        for item in value:
                            cf.write(f"{key}={item}\n")
                    else:
                        cf.write(f"{key}={value}\n")
                
                # Insert newline after each section and at the end of the file
                cf.write("\n")
    
    def clear(self) -> None:
        """ Clears the config """
        self._dict.clear()
        
    def clone(self) -> INIMultiConfig:
        """ Returns a new INIMultiConfig instance with the same data """
        return INIMultiConfig(config_dict=self.get_dict())

    @staticmethod
    def _rec_update(base_dict: dict, update_with_dict: dict) -> dict:
        """
            Update {base_dict} with the values of {update_with_dict} recursively and add missing values
        """
        
        updated_dict = {}
        
        # For every key that is both in base_dict and update_with_dict,
        # add key to updated_dict with value of update_with_dict
        # and for every value that is a dictionary, execute the method recursively
        for key, value in base_dict.items():
            if not (key in update_with_dict):
                updated_dict[key] = value
            else:
                if isinstance(value, dict):
                    updated_dict[key] = INIMultiConfig._rec_update(value, update_with_dict[key])
                else:
                    updated_dict[key] = update_with_dict[key]
        
        # Add every key and value in update_with_dict, but not in base_dict to updated_dict
        for key, value in update_with_dict.items():
            if key not in updated_dict:
                updated_dict[key] = value
        
        return updated_dict
    
    @staticmethod
    def get_encoding(file_path: str) -> str:
        """
            Creates the file path and file specified in {file_path} if needed(utf-8) and returns its encoding.
        """
        
        path_dir = path.dirname(file_path)
        
        # If directory containing file doesn't exist yet, create it and all requred directories
        if path_dir and (not path.exists(path_dir)):
            os.makedirs(path_dir)
        
        # Try to open file with encoding "utf-8"
        with open(file_path, "a+", encoding="utf_8"):
            pass
        
        # Determine encoding of file at file_path
        with open(file_path, "rb") as file:
            rawdata = file.read()
        
        result = chardet.detect(rawdata)
        charenc = result["encoding"]
        
        return charenc
    
    def update(self, update_with_dict: dict) -> None:
        """ Update this config with the values from {update_with_dict} """
        
        self.read_dict(INIMultiConfig._rec_update(self.get_dict(), update_with_dict))
    
    def overwrite_with(self, overwrite_dict: dict) -> INIMultiConfig:
        """ Updates this config with the values in {overwrite_dict} and returns this config object """
        
        overwrite_config = INIMultiConfig(config_dict=overwrite_dict)
        
        self.update(overwrite_config.get_dict())
        
        return self
    
    def baseline(self, baseline_dict: dict) -> INIMultiConfig:
        """
            Adds sections and key-value-pairs from {baseline_dict} whose keys don't already exist to this config and returns this config object
        """
        
        baseline_config = INIMultiConfig(config_dict=baseline_dict)
        
        baseline_config.update(self.get_dict())
        self.read_dict(baseline_config.get_dict())
        
        return self