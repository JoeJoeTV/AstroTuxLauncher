#
# This file is heavily based upon AstroRCON.py from [AstroLauncher](https://github.com/ricky-davis/AstroLauncher)
#

import socket
import json
import time
from enum import Enum

class PlayerCategory(Enum):
    UNLISTED = "Unlisted"
    BLACKLISTED = "Blacklisted"
    WHITELISTED = "Whitelisted"
    ADMIN = "Admin"
    PENDING = "Pending"
    OWNER = "Owner"

#TODO: Maybe Thread safety using mutex lock

class AstroRCON():
    """
        Class for communicating with an Astroneer Dedicated Server using RCON over TCP.
        Arguments:
            - port: The RCON port of the Astroneer Server
            - password: The password used to authenticate the RCON connection to the dedicated server
            - [ip]: The IP where the dedicated server is located (Default: Only local)
    """
    
    def __init__(self, port, password=None, ip="127.0.0.1"):
        self.port = port
        self.password = password
        self.ip = ip
        
        self.socket = None
        self.connected = False
    
    def _createSocket(self):
        """ Creates a new TCP IPv4 socket """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    def disconnect(self):
        self.connected = False
        
        try:
            self.socket.close()
            self.socket = None
        except:
            pass
    
    def connect(self):
        """ Tries to connect to the dedciated server RCON port """
        # If no socket exists, create new one
        if (self.socket is None):
            self._createSocket()
        
        # If already connected, do nothing
        if self.connected:
            return
        
        # Connect to Astroneer Server RCON port
        self.socket.connect((self.ip, self.port))
        
        if not (self.password is None):
            
            # Send RCON password to authenticate connection
            self.socket.sendall(f"{self.password}\n".encode())
        
        self.connected = True
    
    def ensureConnection(self):
        """ Try to connect if not connected and check the connection. Returns the connected status """
        
        # If not connected or socket is None, try to connect
        if (not self.connected) or (self.socket is None):
            try:
                self.connect()
            except:
                pass
        
        # Check connection by sending small message
        try:
            self.socket.send(b"Hello There!\n")
        except:
            self.connected = False
            self.socket.close()
            self.socket = None
        
        return self.connected
    
    def _recvMessage(self):
        """ Receive and parse data from socket """
        
        raw_data = self._recvall()
        return AstroRCON.parseRawData(raw_data)
    
    def _recvall(self):
        """ Tries receiving chunks until the data has fully been sent. Returns the received data as bytes"""
        
        # If not connected, don't return anything
        if not self.connected:
            return None
        
        try:
            BUFF_SIZE = 4096
            data_buf = b""
            
            while True:
                # Receive data chunk and append to data buffer
                chunk = self.socket.recv(BUFF_SIZE)
                data_buf += chunk
                
                #print("[RCON] Received Chunk:", str(chunk))
                
                # If data chunk size was smaller than requested size (or 0), break, since end of data has been supposedly reached
                if len(chunk) < BUFF_SIZE:
                    break
            
            # We've hopefully received the full data block, so return it
            return data_buf
        except:
            # Error happened during receiving, so return nothing
            return None
    
    @staticmethod
    def parseRawData(raw_data):
        """ Tries parsing raw_data as JSON and if not possible, returns raw data """
        
        try:
            if raw_data != b"":
                # Data is not empty, try to parse JSON
                raw_data = raw_data.rstrip()
                json_data = json.loads(raw_data.decode())
                
                return json_data
        except:
            # Couldn't parse JSON, return raw data
            return raw_data
    
    def _sendreceive(self, data, recvdata=True):
        """
            Send data to socket and possibly receive response data if {recvdata} is True.
            Enters the disconnected state, if the sending of data produces an arror.
            
            Arguments:
                - data: The data to send to the socket
                - [recvdata]: Wether to expect and receive response data
            
            Returns:
                - response data, if {recvdata} is True and data was successfully sent ad response data successfully received
                - True, if {recvdata} is false and the sending was successful
                - None, if we're not connected, the data is empty or an error occurred wile sending or receiving
        """
        
        # If we're not connected or data is empty, immediately return
        if (not self.connected) or (len(data) == 0):
            return None

        # Try to send data
        try:
            self.socket.sendall(data)
        except:
            # If we get an exception, assume the connection was broken and enter disconnected state
            self.disconnect()
            return None
        
        # If we don't want to receive data following the sending, we're finished
        if not recvdata:
            return True
        
        # Receive answer data
        try:
            response = self._recvMessage()
            return response
        except:
            return None
        
    #
    #   Functions to send Commands to the server
    #
    
    def DSSetPlayerCategoryForPlayerName(self, playerName, category):
        """
            Sends the 'DSSetPlayerCategoryForPlayerName' command to the Dedicated Server.
            
            CMD Description: Set a player's category based on the player's name.
            
            Arguments:
                - playerName: The name of the player
                - category a PlayerCategory representing the category to set
            
            Returns: Received Data
        """
        
        # Escape quotation marks in player name
        escapedName = playerName.replace('"', '\\"')
        
        return self._sendreceive(f'DSSetPlayerCategoryForPlayerName "{escapedName}" {category.value}\n'.encode(), True)
    
    def DSSetDenyUnlisted(self, state):
        """
            Sends the 'DSSetDenyUnlisted' command to the Dedicated Server.
            
            CMD Description: Enable or disable the whitelist
            
            Arguments:
                - state: Wether the Whitelist should be enabled or not
            
            Returns: Received Data
        """
        
        return self._sendreceive(f'DSSetDenyUnlisted {str(state).lower()}\n'.encode(), True)
    
    def DSKickPlayerGuid(self, playerGuid):
        """
            Sends the 'DSKickPlayerGuid' command to the Dedicated Server.
            
            CMD Description: Kick a player based on their guid
            
            Arguments:
                - playerGuid: The Guid of the Player that should be kicked
            
            Returns: Received Data
        """
        
        return self._sendreceive(f'DSKickPlayerGuid {str(playerGuid)}\n'.encode(), True)
    
    def DSServerStatistics(self):
        """
            Sends the 'DSServerStatistics' command to the Dedicated Server.
            
            CMD Description: Get information about the server
            
            Returns: Received Data
        """
        
        return self._sendreceive(f'DSServerStatistics\n'.encode(), True)
    
    def DSListPlayers(self):
        """
            Sends the 'DSListPlayers' command to the Dedicated Server.
            
            CMD Description: Get the known players list
            
            Returns: Received Data
        """
        
        return self._sendreceive(f'DSListPlayers\n'.encode(), True)
    
    def DSLoadGame(self, saveName):
        """
            Sends the 'DSLoadGame' command to the Dedicated Server.
            
            CMD Description: Load a new save and set it as the active save for the server
            
            Returns: True if successfully sent command
        """
        
        return self._sendreceive(f'DSLoadGame {saveName}\n'.encode(), True)
    
    def DSSaveGame(self, name=None):
        """
            Sends the 'DSSaveGame' command to the Dedicated Server.
            
            CMD Description: Save the game instantly
            
            Arguments:
                - name(optional): Name to save game as
            
            Returns: True if successfully sent command
        """
        
        if (name is None):
            response = self._sendreceive(f'DSSaveGame\n'.encode(), False)
        else:
            response = self._sendreceive(f'DSSaveGame {name}\n'.encode(), False)
        
        if (response is None):
            return response
        else:
            time.sleep(1.1)
            return response
    
    def DSNewGame(self, save_name=None):
        """
            Sends the 'DSNewGame' command to the Dedicated Server.
            
            CMD Description: Create a new save and set it as active. All players will be forced to reload.
            
            Arguments:
                - saveName: The name of the new save
            
            Returns: True if successfully sent command
        """
        
        if save_name is None:
            return self._sendreceive(f'DSNewGame\n'.encode(), False)
        else:
            return self._sendreceive(f'DSNewGame {save_name}\n'.encode(), False)
    
    def DSServerShutdown(self):
        """
            Sends the 'DSServerShutdown' command to the Dedicated Server.
            
            CMD Description: Shutdown the server gracefully
            
            Returns: True if successfully sent command
        """
        
        return self._sendreceive(f'DSServerShutdown\n'.encode(), False)
    
    def DSListGames(self):
        """
            Sends the 'DSListGames' command to the Dedicated Server.
            
            CMD Description: List all the saves available
            
            Returns: Received Data
        """
        
        return self._sendreceive(f'DSListGames\n'.encode(), True)
