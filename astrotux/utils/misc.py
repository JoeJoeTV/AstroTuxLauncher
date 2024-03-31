import common

# 
# File: utils/misc.py
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


# Exception classes to be used in the project
class GeneralError(Exception):
    """ General error, which should be logged, but doesn't necessarily cause the program to exit """
    
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class FatalError(GeneralError):
    """ Fatal error, which should be logged and cause the program to exit """
    
    def __init__(self, message, exit_reason):
        self.message = message
        self.exit_reason = exit_reason
        super().__init__(self.message)