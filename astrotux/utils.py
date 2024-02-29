import common

# 
# File: utils.py
# Description: Smaller utility functions
#

def ensure_python_version():
    """ 
    Makes sure, that the Python version is at least 3.9, as versions below that are not supported.
    If the python version is too old, the function will quit with a message notifying the user.
    """
    
    if (sys.version_info.major < 3) or ((sys.version_info.major == 3) and (sys.version_info.minor < 9)):
        print()
        print(f"ERROR:   {common.APPLICATION_NAME} needs at least Python 3.9 to run properly!")
        print(f"         You are currently running version {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}.")
        print()
        sys.exit(1)
