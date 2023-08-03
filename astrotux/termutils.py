# Library for interacting with the terminal using ANSI Escape Sequences

class ANSI:
    
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
    print('\33]0;' + title + '\a', end='', flush=True)