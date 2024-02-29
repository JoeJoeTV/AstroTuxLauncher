# 
# File: utils/terminal.py
# Description: Utilities for working with terminal input/output
#

from sys import stdin, stdout
from platform import system
import os

class ANSICtrl:
    """
        Provides support for ANSI control codes
    """
    
    @staticmethod
    def _esc_base(code):
        return bytes.fromhex("1b").decode() + code

    @staticmethod
    def home():
        print(ANSI._esc_base("[H"), end="", flush=True)
    
    @staticmethod
    def goto(line, column):
        print(ANSI._esc_base(f"[{line};{column}H"), end="", flush=True)
    
    @staticmethod
    def clear_screen():
        print(ANSI._esc_base("[2J"), end="", flush=True)
    
    @staticmethod
    def clear_line():
        print(ANSI._esc_base("[2K"), end="", flush=True)
    
    @staticmethod
    def clear_line_from_cursor():
        print(ANSI._esc_base("[0K"), end="", flush=True)
    
    @staticmethod
    def cursor_invisible():
        print(ANSI._esc_base("[?25l"), end="", flush=True)
    
    @staticmethod
    def cursor_visible():
        print(ANSI._esc_base("[?25h"), end="", flush=True)
    
    @staticmethod
    def enable_alt_buffer():
        print(ANSI._esc_base("[?1049h"), end="", flush=True)
    
    @staticmethod
    def disable_alt_buffer():
        print(ANSI._esc_base("[?1049l"), end="", flush=True)


def set_window_title(title):
    """ Sets the terminal windows title to the specified string """
    print('\33]0;' + title + '\a', end='', flush=True)

# Check if terminal supports ANSI Control Codes. See https://stackoverflow.com/a/75703990/11286087
if system() == "Windows":
    from msvcrt import getch, kbhit

else:
    from termios import TCSADRAIN, tcgetattr, tcsetattr
    from select import select
    from tty import setraw
    from sys import stdin

    def getch() -> bytes:
        fd = stdin.fileno()
        old_settings = tcgetattr(fd)

        try:
            setraw(fd)

            return stdin.read(1).encode()
        finally:
            tcsetattr(fd, TCSADRAIN, old_settings)

    def kbhit() -> bool:
        return bool(select([stdin], [], [], 0)[0])

def _isansitty() -> bool:
    """
    Checks if stdout supports ANSI escape codes and is a tty.
    """

    while kbhit():
        getch()

    stdout.write("\x1b[6n")
    stdout.flush()

    stdin.flush()
    if kbhit():
        if ord(getch()) == 27 and kbhit():
            if getch() == b"[":
                while kbhit():
                    getch()

                return stdout.isatty()

    return False

def check_term_ansi_support():
    """
    Checks if the terminal supports all ANSI control codes, only color codes or doesn't support ANSI control codes at all.
    Return:
        - True, if the terminal has full ANSI support
        - False, if only color control codes are supported
        - None, if the terminal has no ANSI support at all
    """
    
    if not _isansitty():
        return None
    else:
        return ("TERM" in os.environ) and ("coloronly" not in os.environ["TERM"])

# Hack to detect wether UTF-8 symbols in the progress bar will cause problems
def check_utf8_symbol_support():
    # Print character that causes problems and if an error occurs, we know that we can't use fancy symbols
    try:
        print('\u28f7', end="", flush=True)
        ANSI.clear_line()
        print("\r", end="", flush=True)
        return True
    except UnicodeEncodeError:
        return False