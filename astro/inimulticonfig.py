#
# This file is based upon code from [AstroLauncher](https://github.com/ricky-davis/AstroLauncher)
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
    
    def __init__(self, confDict=None, filePath=None):
        """
            Create new config object. If {filePath} is specified, load config from specified .ini file.
            Else, if {confDict} is specified, load config from passed dictionary.
            If none is specified, create empty config object
        """
        
        self._dict = {}
        
        if not (filePath is None):
            self.read_file(filePath)
        elif not (confDict is None) and isinstance(confDict, dict):
            self.read_dict(confDict)
    
    def __getitem__(self, key):
        """ Is used, such that values can be accessed like in a dictionary """
        return self._dict[key]
    
    def set_value(self, section, key, value, append=False):
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
        
    def get_dict(self):
        """ Returns the dictionary containing the data of the config """
        return self._dict.copy()
    
    def sections(self):
        """ Returns a set representing the sections currently present in the config """
        return self._dict.keys()
    
    def read_dict(self, configDict):
        """ Reads the given dictionary {configDict} as config data """
        
        # If {configDict} is not a dictionary, do nothing
        if not isinstance(configDict, dict):
            return
        
        # If any section name doesn't reference a dictionary, return
        for _, section in configDict.items():
            if not isinstance(section, dict):
                return

        self._dict = json.loads(json.dumps(configDict), parse_int=str, parse_float=str)
    
    def read_file(self, configPath):
        """
            Reads the specified INI file
            
            Arguments:
                - configPath: Path to the .ini file
        """
        
        encoding = INIMultiConfig.get_encoding(configPath)
        
        with open(configPath, "r", encoding=encoding) as cf:
            lines = [line.strip() for line in cf.read().split("\n")]
            
            # Note: The "Global" section will be ignored
            currentSection = None
            
            while len(lines) > 0:
                # Get first line and split by separator
                line = lines.pop(0).split("=", 1)
                
                # If we only have one element after split that is surrounded by square brackets, it's a section header
                if (len(line) == 1) and (len(line[0]) >= 2) and (line[0][0] == "[") and (line[0][-1] == "]"):
                    # We have a section header
                    
                    # New section header
                    newSection = line[0][1:-1].strip()
                    
                    # Only set new section, if length of header
                    if (len(newSection) > 0):
                        currentSection = newSection
                        self._dict[currentSection] = {}
                    
                elif (len(line) > 1):
                    # We have a property
                    
                    # If we're not in a named section, ignore value
                    if (currentSection is None):
                        continue
                    
                    key = line[0].strip()
                    value = line[1].strip()
                    
                    # If the value looks like a boolean, convert it using mapping table
                    if value.lower() in INIMultiConfig.BOOLEAN_STATES:
                        value = INIMultiConfig.BOOLEAN_STATES[value.lower()]
                    
                    if not (key in self._dict[currentSection]):
                        # If the key does not already exist, create it and assign the value
                        
                        self._dict[currentSection][key] = value
                    else:
                        if isinstance(self._dict[currentSection][key], list):
                            # If the key already exists and is a list, add the value to the list
                            
                            self._dict[currentSection][key].append(value)
                        else:
                            # If the key already exists and is NOT a list, create a new list and add it to the list
                            
                            self._dict[currentSection][key] = [self._dict[currentSection][key], value]
    
    def write_file(self, configPath):
        """
            Writes the configuration to the specified file
            
            Arguments:
                - configPath: Path where the config file should be written
                - overwrite: Wether an error should be thrown, if the file already esists(False) or not(True)
        """
        
        encoding = INIMultiConfig.get_encoding(configPath)
        
        with open(configPath, "w", encoding=encoding) as cf:
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
    
    def clear(self):
        """ Clears the config """
        self._dict.clear()
        
    def clone(self):
        """ Returns a new INIMultiConfig instance with the same data """
        return INIMultiConfig(confDict=self.get_dict())

    @staticmethod
    def _rec_update(baseDict, updateWithDict):
        """
            Update {baseDict} with the values of {updateWithDict} recursively and add missing values
        """
        
        updatedDict = {}
        
        # For every key that is both in baseDict and updateWithDict,
        # add key to updatedDict with value of updateWithDict
        # and for every value that is a dictionary, execute the method recursively
        for key, value in baseDict.items():
            if not (key in updateWithDict):
                updatedDict[key] = value
            else:
                if isinstance(value, dict):
                    updatedDict[key] = INIMultiConfig._rec_update(value, updateWithDict[key])
                else:
                    updatedDict[key] = updateWithDict[key]
        
        # Add every key and value in updateWithDict, but not in baseDict to updatedDict
        for key, value in updateWithDict.items():
            if key not in updatedDict:
                updatedDict[key] = value
        
        return updatedDict
    
    @staticmethod
    def get_encoding(filePath):
        """
            Creates the file path and file specified in {filePath} if needed(utf-8) and returns its encoding.
        """
        
        pathDir = path.dirname(filePath)
        
        # If directory containing file doesn't exist yet, create it and all requred directories
        if pathDir and (not path.exists(pathDir)):
            os.makedirs(pathDir)
        
        # Try to open file with encoding "utf-8"
        with open(filePath, "a+", encoding="utf_8"):
            pass
        
        # Determine encoding of file at filePath
        with open(filePath, "rb") as file:
            rawdata = file.read()
        
        result = chardet.detect(rawdata)
        charenc = result["encoding"]
        
        return charenc
    
    def update(self, updateWithDict):
        """ Update this config with the values from {updateWithDict} """
        
        self.read_dict(INIMultiConfig._rec_update(self.get_dict(), updateWithDict))
    
    def overwrite_with(self, overwriteDict):
        """ Updates this config with the values in {overwriteDict} and returns this config object """
        
        overwriteConfig = INIMultiConfig(confDict=overwriteDict)
        
        self.update(overwriteConfig.get_dict())
        
        return self
    
    def baseline(self, baselineDict):
        """
            Adds sections and key-value-pairs from {baselineDict} whose keys don't already exist to this config and returns this config object
        """
        
        baselineConfig = INIMultiConfig(confDict=baselineDict)
        
        baselineConfig.update(self.get_dict())
        self.read_dict(baselineConfig.get_dict())
        
        return self