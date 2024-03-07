import inspect
from textwrap import dedent
from enum import Enum
import threading
import logging

WHITESPACE = [
    " ",
    "\t",
    "\n"
]

QUOTES = ['"', "'"]

class CMDParserError(Exception):
    def __init__(self, input_str, index, message):
        self.input_str = input_str
        self.index = index
        self.message = f"{message} [Column {self.index} | Here: ...{self.input_str[self.index-3:self.index]} >{self.input_str[self.index]}< {self.input_str[self.index+1:self.index+4]}...]"
        super().__init__(message)

def parse_cmd(raw_input):
    parsed_args = []
    
    # Parsing state
    quote_ctx = ""
    word_start = 0
    prev_char = ""
    
    for i, c in enumerate(raw_input):
        if c in WHITESPACE:
            # Current character is whitespace
            
            if not quote_ctx and prev_char and (prev_char not in WHITESPACE) and (prev_char not in QUOTES):
                # If this whitespace follows a normal character (not whitespace, not quote, not start), save new word
                parsed_args.append(raw_input[word_start:i])
        elif c in QUOTES:
            # Current character is a quote
            
            if quote_ctx and (c == quote_ctx):
                # If we encounter the closing quote (quote ctx is set and quote char is equal), add new word and reset the quote ctx
                parsed_args.append(raw_input[word_start+1:i])
                quote_ctx = ""
            elif not quote_ctx:
                if (not prev_char) or (prev_char in WHITESPACE):
                    # If we encounter a starting quote (quote ctx not set and previous char is start or whitespace), set the quote ctx and word start index
                    quote_ctx = c
                    word_start = i
                else:
                    # If we encounter a starting qoute (quote ctx not set and previous char is start or whitespace) and the previous character is not whitespace or the start, throw an error
                    raise CMDParserError(raw_input, i, "Missing whitespace before starting quote")
        else:
            # Current character is a normal character
            
            if not quote_ctx:
                if (not prev_char) or (prev_char in WHITESPACE):
                    # If we encounter a normal character (not whitespace, not quote) and the previous character is a whitespace or the start, we know that a new word begins, so we can set the start index
                    word_start = i
                elif prev_char and (prev_char in QUOTES):
                    # If we encounter a normal character (not whitespace, not quote) and the previous character is a quote, whitespace is missing, so throw an error
                    raise CMDParserError(raw_input, i, "Missing whitespace after closing quote")

        # Update variable with current char for next iteration to avoid backwards lookups
        prev_char = c
    
    if quote_ctx:
        # If after parsing the quote context is still set, we know that there is a missing closing quote
        raise CMDParserError(raw_input, len(raw_input)-1, f"Missing closing quote: {quote_ctx}")

    if prev_char and (prev_char not in WHITESPACE) and (prev_char not in QUOTES):
        # If an arguments goes until the end of the string (so the last character is not a quote or whitespace), we need to add it afterwards
        parsed_args.append(raw_input[word_start:len(raw_input)])
    
    return parsed_args

class MissingArgumentError(Exception):
    def __init__(self, argument: str, arg_type: type, message: str = None):
        self.argument = argument
        self.arg_type = arg_type
        self.message = message
        super().__init__(message)

class ArgumentTypeError(Exception):
    def __init__(self, argument: str, expected_type: type, given_type: type, message: str = None):
        self.argument = argument
        self.expected_type = expected_type
        self.given_type = given_type
        self.message = message
        super().__init__(message)

class UnexpectedArgumentError(Exception):
    def __init__(self, additional_args: str|list, message: str = None):
        self.additional_args = additional_args
        self.message = message
        super().__init__(message)

class ExecutionError(Exception):
    def __init__(self, command: type, message: str = None, exception: Exception = None):
        self.command = command
        self.message = message
        self.exception = exception
        super().__init__(message)

class Arg:
    def __init__(self, arg_type: type, optional: bool = False, description: None|str = None):
        self.arg_type = arg_type
        self.optional = optional
        self.description = description
    
    def __repr__(self):
        return f"Arg(type={self.arg_type}, optional={self.optional}, description={self.description})"

BOOL_STRINGS = {
    True: ["true", "yes", "t", "y", "1"],
    False: ["false", "no", "f", "n", "0"],
}

def str_to_bool(string: str) -> bool:
    if string.lower() in BOOL_STRINGS[True]:
        return True
    elif string.lower() in BOOL_STRINGS[False]:
        return False
    else:
        raise ValueError(f"String '{string}' is not a valid boolean string")

def get_type_description(t: type) -> str:
    if issubclass(t, bool):
        return f"{t.__name__}: {'/'.join(BOOL_STRINGS[True])}, {'/'.join(BOOL_STRINGS[False])}"
    elif issubclass(t, Enum):
        return f"{t.__name__}: {','.join([str(e.value) for e in t])}"
    else:
        return t.__name__

class Command:
    # Configuration options for command
    description: str = None
    
    # Internal variables
    _args = None
    
    @classmethod
    def args(cls):
        """ Class method used for getting the available arguments for this command class """
        
        # If a previous call already saved the available arguments, we don't need to regenerate them
        if cls._args is not None:
            return cls._args
        
        args = {
            "req": {},
            "opt": {}
        }
        
        for n, v in inspect.get_annotations(cls).items():
            if not isinstance(v, Arg):
                continue
            
            if v.optional:
                args["opt"][n] = v
                setattr(cls, n, None)
            else:
                args["req"][n] = v
        
        cls._args = args
        
        return cls._args
    
    def __init__(self, passed_args: list, name: str):
        self.name = name
        
        # Check required arguments
        for a, v in self.args()["req"].items():
            if len(passed_args) == 0:
                raise MissingArgumentError(a, v.arg_type, f"Required argument {a} is not specified")
            
            val = passed_args.pop(0)
            
            try:
                if v.arg_type is bool:
                    val = str_to_bool(val)
                else:
                    val = v.arg_type(val)
            except:
                raise ArgumentTypeError(a, v.arg_type, type(val), f"Can't convert from given type {type(val)} to expected type {v.arg_type} for required argument {a}")
            
            self.__dict__[a] = val

        # Check optional arguments
        for a, v in self.args()["opt"].items():
            if len(passed_args) == 0:
                break
            
            val = passed_args.pop(0)
            
            try:
                if val is bool:
                    val = str_to_bool(val)
                else:
                    val = v.arg_type(val)
            except:
                raise ArgumentTypeError(a, v.arg_type, type(val), f"Can't convert from given type {type(val)} to expected type {v.arg_type} for optional argument {a}")
            
            self.__dict__[a] = val
        
        # If at the end, there are still arguments left, produce error
        if len(passed_args) > 0:
            raise UnexpectedArgumentError(passed_args, f"Encountered unexpected additional argument(s): {' '.join(passed_args)}")
    
    def execute(self, data = None, parent = None):
        """ Executes the command """
        # To be overridden by subclasses
        pass
    
    @classmethod
    def help_text(cls, path) -> [str, str]:        
        usage_str = " ".join( \
            [f"<{argname}>" for argname in cls.args()["req"]] \
            + [f"[{argname}]" for argname in cls.args()["opt"]])
        
        help_str_list = []
        
        if cls.description:
            help_str_list.append(f"Description:\n  {cls.description}")

        def help_str_for_argmap(argmap, title):
            maxlen = max(len(argname) for argname in argmap)
            return title + ":\n  " \
                + "\n  ".join([f"{n.ljust(maxlen)}  {a.description+chr(10)+'    '+(' '*maxlen) if a.description is not None else ''}({get_type_description(a.arg_type)})" for n, a in argmap.items()])

        if len(cls.args()["req"]) > 0:
            help_str_list.append(help_str_for_argmap(cls.args()["req"], "Required Arguments"))
        
        
        if len(cls.args()["opt"]) > 0:
            help_str_list.append(help_str_for_argmap(cls.args()["opt"], "Optional Arguments"))

        return usage_str, "\n\n".join(help_str_list)

class ParentCommand(Command):
    # Configuration options for parent command
    subcmd_required = True
    
    @classmethod
    def args(cls):
        """ Class method used for getting the available subcommands for this command class """
        
        # If a previous call already saved the available subcommands, we don't need to regenerate them
        if cls._args is not None:
            return cls._args
        
        args = {}
        
        for n, v in inspect.get_annotations(cls).items():
            if not issubclass(v, Command):
                continue
            
            args[n] = v
        
        cls._args = args
        
        return cls._args
        
    def __init__(self, passed_args: list, name: str = "root"):
        self.name = name
        self.child = None
        
        if len(passed_args) == 0:
            if self.subcmd_required:
                raise MissingArgumentError("subcommand", Command, "Required subcommand is not specified")
            return
        
        val = passed_args.pop(0)
        
        if val in self.args():
            self.child = self.args()[val](name=val, passed_args=passed_args)
        else:
            raise MissingArgumentError("subcommand", Command, f"Encountered unknown subcommand: {val}")
    
    def execute(self, data = None, parent = None):
        if self.child is not None:
            self.child.execute(data=data, parent=self.__class__)
        else:
            self._execute_standalone(data=data, parent=parent)
    
    def execute_standalone(self, data = None, parent = None):
        """ Executes the command if no subcommand is given """
        # To be overridden by subclasses
        pass
    
    @classmethod
    def help_text(cls, path) -> [str, str]: 
        if (len(path) == 0) or (path[0] not in cls.args()):
            # Case: No further path element exists or matches any subcommand, so display help of this command
            
            usage_str = "<subcommand>" if cls.subcmd_required else "[subcommand]"
            
            help_str_list = []
            
            if cls.description:
                help_str_list.append(f"Description:\n  {cls.description}")
            
            if len(cls.args()) > 0:
                maxlen = max(len(argname) for argname in cls.args())
                help_str_list.append("Subcommands:\n  " \
                    + "\n  ".join([f"{n.ljust(maxlen)}  {a.description if a.description is not None else ''}" for n, a in cls.args().items()]))
            
            help_str = "\n\n".join(help_str_list)
        else:
            # Case: First path element matches some subcommand, so get help text recursively
            
            subcmd = path.pop(0)
            
            usage_str, help_str = cls.args()[subcmd].help_text(path)

            usage_str = f"{subcmd} {usage_str}"
        
        return usage_str, help_str

CLI_LOGGER = logging.getLogger("CLI") 

class CLIThread(threading.Thread):
    """
        Class for asynchronously handling the CLI interface for the launcher
    """

    def __init__(self, cli_model: type[Command], launcher, active: bool = False, name: str = "cli-thread"):
        self.cli_model = cli_model
        self.launcher = launcher
        self.active = active
        
        super().__init__(name=name)
        
        self.daemon = True
    
    def excepthook(self, args):
        CLI_LOGGER.error(f"An unexpected error occured in the CLI thread ({args.exc_type}). For more info, see debug log.")
        CLI_LOGGER.debug(f"{args.exc_type}: {args.exc_value}\n{args.exc_traceback}")
    
    def set_active(self, active=True):
        if active != self.active:
            self.active = active
            CLI_LOGGER.debug(f"Toggled active state of the cli thread: {active}")
    
    def run(self):
        while True:
            input_string = input()
            
            if not self.active:
                continue
            
            CLI_LOGGER.debug(f"Raw input: {input_string}")
            
            try:
                cmd_args = parse_cmd(input_string)
            except CMDParserError as e:
                CLI_LOGGER.error(f"Syntax Error: {e.message}")
                continue
            
            try:
                cmd = self.cli_model(cmd_args)
            except MissingArgumentError as e:
                CLI_LOGGER.error(f"Syntax Error - Missing Argument: {e.message}")
                continue
            except ArgumentTypeError as e:
                CLI_LOGGER.error(f"Syntax Error - Wrong Argument Type: {e.message}")
                continue
            except UnexpectedArgumentError as e:
                CLI_LOGGER.error(f"Syntax Error - Unexpected Argument(s): {e.message}")
                continue
            
            try:
                cmd.execute(self.launcher)
            except ExecutionError as e:
                CLI_LOGGER.error(f"There was an error while executing the command: {e.message}")
                if e.exception is not None:
                    CLI_LOGGER.debug(f"Original Exception: {e.exception}")