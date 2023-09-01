from os import path
import os

LAUNCHER_VERSION="1.1.0"

CONTROL_CODES_SUPPORTED = None

# If TERM environment variable contains "coloronly", disable stuff that uses ANSI escape codes other than color
if ("TERM" in os.environ) and ("coloronly" in os.environ["TERM"]):
    CONTROL_CODES_SUPPORTED = False

def ExcludeIfNone(value):
    """Do not include field for None values"""
    return value is None

def read_build_version(astro_path):
    """ Read build version of Astroneer Server installation using the 'build.version file' """
    
    verfile_path = path.join(astro_path, "build.version")
    
    # If file doesn't exist, assume no installation is present
    if not path.isfile(verfile_path):
        return None
    
    with open(verfile_path, "r") as vf:
        verstring = vf.readline()[:-10]
    
    return verstring.strip()