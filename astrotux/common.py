import os
import termutils

# 
# File: common.py
# Description: Common Constants, Variable and functions for the whole project
#

APPLICATION_NAME = "AstroTuxLauncher"

# The current version of AstroTuxLauncher
LAUNCHER_VERSION = "1.1.7"

# Some Environment properties
ENV_SUPPORTS_FULL_ANSI = termutils.check_term_ansi_support()
ENV_SUPPORTS_UTF8_CHARS = termutils.check_utf8_symbol_support()
