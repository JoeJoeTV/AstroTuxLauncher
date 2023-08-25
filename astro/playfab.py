#
# This file is heavily based upon code from [AstroLauncher](https://github.com/ricky-davis/AstroLauncher)
#

import json
import urllib
import urllib.error
from urllib import request
import ssl
import time
from utils.net import get_request, post_request
import logging

#
#   Methods for interacting with the Playfab Astroneer API
#

base_headers = {
    "Content-Type": "application/json; charset=utf-8",
    "X-PlayFabSDK": "UE4MKPL-1.49.201027",
    "User-Agent": "Astro/++UE4+Release-4.23-CL-0 Windows/10.0.19042.1.256.64bit"
}

class APIError(Exception):
    
    def __init__(self, message="A Playfab API error occured"):
        self.message = message
        super().__init__(self.message)

def check_api_health():
    """
        Checks the the Playfab API is available
        
        Returns: A boolean value indicating if the API is available
    """
    
    url = "https://5ea1.playfabapi.com/"
    
    try:
        resp = json.load(get_request(url))
        
        return resp["Healthy"] == True
    except Exception as e:
        logging.debug(f"Error while checking for Playfab API health: {str(e)}")
        return False

def generate_XAuth(serverGUID):
    """
        Generates an X-Authorization token to use for further communication with Playfab
        
        Arguments:
            - serverGUID: The GUID of the server, such that an account can be requested
        
        Returns: A session ticket to be used as X-Authorization
    """
    
    url = f"https://5EA1.playfabapi.com/Client/LoginWithCustomID?sdk={base_headers['X-PlayFabSDK']}"
    
    # First, check for existing account
    requestObject = {
        "CreateAccount": False,
        "CustomId": serverGUID,
        "TitleId": "5EA1"
    }
    
    response = json.load(post_request(url, headers=base_headers, jsonData=requestObject))
    
    # If account doesn't exist, create new one
    if (response["code"] == 400) and (response["error"] == "AccountNotFound"):
        time.sleep(0.2)
        
        requestObject["CreateAccount"] = True
        
        response = json.load(post_request(url, headers=base_headers, jsonData=requestObject))
    
    return response["data"]["SessionTicket"]

def get_server(IPPortCombo, XAuth):
    """
        Requests data from Playfab about the registered servers with matching IP/Port combinations
        
        Arguments:
            - IPPortCombo: The IP/Port combination of the server to get information about
            - XAuth: The session token to be able to use the API
        
        Returns: The requested data or an error status object
    """
    
    url = f"https://5EA1.playfabapi.com/Client/GetCurrentGames?sdk={base_headers['X-PlayFabSDK']}"
    
    # Only return servers that have a matching IP/Port combination
    requestObject = {
        "TagFilter": {
            "Includes": [
                {"Data": {"gameId": IPPortCombo}}
            ]
        }
    }
    
    # Add XAuth header, such that we can use the API
    headers = base_headers.copy()
    headers["X-Authorization"] = XAuth
    
    try:
        response = json.load(post_request(url, headers=headers, jsonData=requestObject))
        
        return response
    except:
        return {"status": "Error"}

def deregister_server(lobbyID, XAuth):
    """
        Deregisters a server identified by the {lobbyID} from Playfab
        
        Arguments:
            - lobbyID: The Lobby ID identifying a registered server
            - XAuth: The session token to be able to use the API
        
        Returns: The status of the operation or an object containing an error status
    """
    
    url = f"https://5EA1.playfabapi.com/Client/ExecuteCloudScript?sdk={base_headers['X-PlayFabSDK']}"
    
    # Deregister Server with matching lobbyID
    requestObject = {
        "FunctionName": "deregisterDedicatedServer",
        "FunctionParameter": {
            "lobbyId": lobbyID
        },
        "GeneratePlayStreamEvent": True
    }
    
    # Add XAuth header, such that we can use the API
    headers = base_headers.copy()
    headers["X-Authorization"] = XAuth
    
    try:
        response = json.load(post_request(url, headers=headers, jsonData=requestObject))
        
        return response
    except:
        return {"status": "Error"}

def heartbeat_server(serverData, XAuth, dataToChange=None):
    """
        Sends a heartbeat using the specified server data
        
        Arguments:
            - serverData: A server data dictionary containing the relevant information for the hearbeat (same as responded by get_server)
            - XAuth: The session token to be able to use the API
            - dataToChange: Dictionary containing values that override values of the FunctionParameter dict of the request object
        
        Returns: The status of the operation or an object containing an error status
    """
    
    url = f"https://5EA1.playfabapi.com/Client/ExecuteCloudScript?sdk={base_headers['X-PlayFabSDK']}"
    
    # Deregister Server with matching lobbyID
    requestObject = {
            "FunctionName": "heartbeatDedicatedServer",
            "FunctionParameter": {
                "serverName": serverData['Tags']['serverName'],
                "buildVersion": serverData['Tags']['gameBuild'],
                "gameMode": serverData['GameMode'],
                "ipAddress": serverData['ServerIPV4Address'],
                "port": serverData['ServerPort'],
                "matchmakerBuild": serverData['BuildVersion'],
                "maxPlayers": serverData['Tags']['maxPlayers'],
                "numPlayers": str(len(serverData['PlayerUserIds'])),
                "lobbyId": serverData['LobbyID'],
                "publicSigningKey": serverData['Tags']['publicSigningKey'],
                "requiresPassword": serverData['Tags']['requiresPassword']
            },
            "GeneratePlayStreamEvent": True
        }
    
    # Add XAuth header, such that we can use the API
    headers = base_headers.copy()
    headers["X-Authorization"] = XAuth
    
    # Override values in FunctionParameter dict using values from {dataToChange}
    if dataToChange is not None:
        requestObject['FunctionParameter'].update(dataToChange)
    
    try:
        response = json.load(post_request(url, headers=headers, jsonData=requestObject))
        
        return response
    except:
        return {"status": "Error"}
    