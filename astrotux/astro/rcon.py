#
# File: astro/rcon.py
# Description: Fuctionality for interacting with the RCON interface provided by the Astroneer Dedicated Server
# Note: This file is heavily based upon AstroRCON.py from [AstroLauncher](https://github.com/ricky-davis/AstroLauncher)
#

import socket, json, time
from enum import Enum
from contextlib import contextmanager
from threading import Lock

class RCONNotConnectedError(Exception):
    """ Exception to be raised, when the RCON is trying to be used while not connected to a server """
    def __init__(self, message="The RCON is not connected to a dedicated server."):
        super().__init__(message)

class RCONDisconnectedError(Exception):
    """ Exception to be raised, when the RCON Connection was disconnected abruptly during an action """
    def __init__(self, message="The RCON Connection was disconnected."):
        super().__init__(message)
        
    

class PlayerCategory(Enum):
    """ Valid player categories used for the RCON """
    
    UNLISTED = "Unlisted"
    BLACKLISTED = "Blacklisted"
    WHITELISTED = "Whitelisted"
    ADMIN = "Admin"
    PENDING = "Pending"
    OWNER = "Owner"

class AstroRCON():
    def __init__(self, port: int, ip: str = "127.0.0.1", password: str|None = None):
        self.port = port
        self.password = password
        self.ip = ip
        
        self.socket = None      # The TCP socket used to communicate with the RCON of the dedicated server
        self.connected = False  # Wether the RCON is currently connected to a dedicated server
        self.lock = Lock()      # Wether the RCON is currently busy
    
    def connect(self) -> bool:
        """ Tries to connect to the dedicated server """
        
        with self.lock:
            # If no socket is present yet, create new TCP socket
            if self.socket is None:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.connected = False
            
            # If the RCON is already connected, do nothing
            if self.connected:
                return True

            # Actually try to connect to socket
            self.socket.connect((self.ip, self.port))
            
            # If password was given we need to send it first
            if self.password is not None:
                self.socket.sendall(f"{self.password}\n".encode())
            
            self.connected = True
            
            return True
    
    def disconnect(self) -> None:
        """ Closes the RCON connection or dies nothing, if not connected """
        with self.lock:
            self.connected = False
            self.socket.close()
            self.socket = None
    
    def check_connection(self) -> bool:
        """ Checks the connection, by sending a small message and checking that no error occurs. Return the connection status """
        
        with self.lock:
            try:
                self.socket.sendall(b"Hello There!\n")
            except:
                self.connected = False
                self.socket.close()
                self.socket = None
            
            return self.connected
    
    def _receive_message(self) -> bytes:
        """ Tries to receive a full message by recv-ing chunks until no data is left. """
        
        if not self.connected:
            raise RCONNotConnectedError()
        
        BUFF_SIZE = 4096
        data_buf = b""
        
        while True:
            # Receive single chunk of data and append it to the data buffer
            chunk = self.socket.recv(BUFF_SIZE)
            
            if chunk:
                data_buf += chunk
                
                if len(chunk) < BUFF_SIZE:
                    break
            else:
                # We got an empty byte string, so the connection has been closed
                self.connected = False
                self.socket.close()
                self.socket = None
                
                raise RCONDisconnectedError()
        
        # We have finished receiving the message, so return the buffer
        return data_buf
    
    @staticmethod
    def _try_parse_json(raw_data: bytes) -> dict|bytes:
        """ Tries to parse the given byte string as JSON data or returns the raw data """
        
        try:
            if raw_data:
                raw_data = raw_data.rstrip()
                json_data = json.loads(raw_data.decode())
                
                return json_data
            
            return b""
        except:
            # Couldn't parse as JSON, so return unmodified
            return raw_data
    
    def _send_receive(self, data: bytes, receive_data: bool = True) -> bool|dict|bytes:
        """
        Sends data and, if specified by the `receive_data` parameter, receives a response to the sent data.
        
        Arguments:
            - data: The data to send to the server
            - [receive_data]: Wether to receive response data
        
        Returns:
            - True, if `receive_data` is False and the data was sent successfully
            - A dict or bytes representing the respone data if `receive_data` is True and the response was received successfully
        """
        
        if not self.connected:
            raise RCONNotConnectedError()
        
        with self.lock:
            # Try to send data
            try:
                self.socket.sendall(data)
            except:
                # An exception occured while sending the data, so assume the connection was closed
                self.connected = False
                self.socket.close()
                self.socket = None
                
                raise RCONDisconnectedError()
            
            # If no data should be received as an answer to the command, we're finished
            if not receive_data:
                return True
            
            # We want to receive an answer, so recieve message and deconde to JSON if possible
            response = self._receive_message()
            return AstroRCON._try_parse_json(response)

    #
    # Functions to send RCON commands to the dedicated server
    #
    
    def DSSetPlayerCategoryForPlayerName(self, player_name: str, category: PlayerCategory) -> dict|bytes:
        """
            Sends the 'DSSetPlayerCategoryForPlayerName' command to the Dedicated Server.
            
            CMD Description: Set a player's category based on the player's name.
            
            Arguments:
                - player_name: The name of the player
                - category: a PlayerCategory representing the category to set the player to
            
            Returns: Received response data (JSON expected)
        """
        
        # Escape quotation marks in player name
        escaped_name = player_name.replace('"', '\\"')
        
        return self._send_receive(f'DSSetPlayerCategoryForPlayerName "{player_name}" {category.value}\n'.encode(), True)
    
    def DSSetDenyUnlisted(self, state: bool) -> dict|bytes:
        """
            Sends the 'DSSetDenyUnlisted' command to the Dedicated Server.
            
            CMD Description: Enable or disable the whitelist
            
            Arguments:
                - state: Wether the Whitelist should be enabled or not
            
            Returns: Received response data
        """
        
        return self._send_receive(f'DSSetDenyUnlisted {str(state).lower()}\n'.encode(), True)
    
    def DSKickPlayerGuid(self, player_guid: str) -> dict|bytes:
        """
            Sends the 'DSKickPlayerGuid' command to the Dedicated Server.
            
            CMD Description: Kick a player based on their guid
            
            Arguments:
                - player_guid: The Guid of the Player that should be kicked
            
            Returns: Received response data
        """
        
        return self._send_receive(f'DSKickPlayerGuid {str(playerGuid)}\n'.encode(), True)

    def DSServerStatistics(self) -> dict|bytes:
        """
            Sends the 'DSServerStatistics' command to the Dedicated Server.
            
            CMD Description: Get information about the server
            
            Returns: Received response data (JSON expected)
        """
        
        return self._send_receive(f'DSServerStatistics\n'.encode(), True)
    
    def DSListPlayers(self) -> dict|bytes:
        """
            Sends the 'DSListPlayers' command to the Dedicated Server.
            
            CMD Description: Get the known players list
            
            Returns: Received response data (JSON expected)
        """
        
        return self._send_receive(f'DSListPlayers\n'.encode(), True)
    
    def DSLoadGame(self, save_name: str) -> dict|bytes:
        """
            Sends the 'DSLoadGame' command to the Dedicated Server.
            
            CMD Description: Load an existing save and set it as the active save for the server
            
            Returns: Received response data (JSON expected)
        """
        
        return self._send_receive(f'DSLoadGame {save_name}\n'.encode(), True)
    
    def DSSaveGame(self, save_name: None|str = None) -> bool:
        """
            Sends the 'DSSaveGame' command to the Dedicated Server.
            
            CMD Description: Save the game instantly. If `save_name` is provided, save the current game with the specified name and set it as the active save
            
            Arguments:
                - [save_name]: Name to save game as
            
            Returns: True if the command was sent successfully
        """
        
        if save_name is None:
            response = self._send_receive(f'DSSaveGame\n'.encode(), False)
        else:
            response = self._send_receive(f'DSSaveGame {save_name}\n'.encode(), False)
        
        return response
    
    def DSNewGame(self, save_name: None|str = None) -> bool:
        """
            Sends the 'DSNewGame' command to the Dedicated Server.
            
            CMD Description: Create a new save and set it as active. All players will be forced to reload.
            
            Arguments:
                - save_name: The name of the new save
            
            Returns: True if the command was sent successfully
        """
        
        if save_name is None:
            return self._send_receive(f'DSNewGame\n'.encode(), False)
        else:
            return self._send_receive(f'DSNewGame {save_name}\n'.encode(), False)
    
    def DSServerShutdown(self) -> bool:
        """
            Sends the 'DSServerShutdown' command to the Dedicated Server.
            
            CMD Description: Shutdown the server gracefully
            
            Returns: True if the command was sent successfully
        """
        
        return self._send_receive(f'DSServerShutdown\n'.encode(), False)
    
    def DSListGames(self) -> dict|bytes:
        """
            Sends the 'DSListGames' command to the Dedicated Server.
            
            CMD Description: List all the saves available
            
            Returns: Received response data (JSON expected)
        """
        
        return self._send_receive(f'DSListGames\n'.encode(), True)