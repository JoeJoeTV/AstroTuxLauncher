#
# File: astro/playfab.py
# Description: Fuctionality for interacting with the Playfab Astroneer API
# Note: This file is heavily based upon AstroAPI.py from [AstroLauncher](https://github.com/ricky-davis/AstroLauncher)
#

from ..utils.net import get_request, post_request
import logging

LOGGER = logging.getLogger("Playfab")

BASE_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "X-PlayFabSDK": "UE4MKPL-1.49.201027",
    "User-Agent": "Astro/++UE4+Release-4.23-CL-0 Windows/10.0.19042.1.256.64bit"
}

PLAYFAB_ASTRO_TITLEID = "5EA1"
PLAYFAB_ASTRO_URL = f"https://{PLAYFAB_ASTRO_TITLEID}.playfabapi.com"

class PlayfabAPIError(Exception):
    def __init__(self, message="An error occured while interacting with the Playfab API"):
        self.message = message
        super().__init__(self.message)

def check_api_health() -> bool:
    """
        Checks if the Playfab API is available.
        
        Returns: A boolean value indicating if the API is available
    """
    
    url = f"{PLAYFAB_ASTRO_URL}/healthstatus"
    
    try:
        response = get_request(url)
        response = json.load(response)
        
        return response["Healthy"] == True
    except Exception as e:
        raise PlayfabAPIError(f"Error while checking for Playfab API health: {str(e)}")

def generate_xauth(server_guid: str) -> str:
    """
        Generates an X-Authorization token to use for further communication with Playfab
        
        Arguments:
            - server_guid: The GUID of the server, such that an account can be requested
        
        Returns: A session ticket to be used as X-Authorization in further requests
    """
    
    url = f"{PLAYFAB_ASTRO_URL}/Client/LoginWithCustomID?sdk={BASE_HEADERS['X-PlayFabSDK']}"
    
    # First, check for existing account
    request_object = {
        "CreateAccount": False,
        "CustomId": server_guid,
        "TitleId": PLAYFAB_ASTRO_TITLEID
    }
    
    response = post_request(url, headers=base_headers, jsonData=request_object)
    response = json.load(response)
    
    # If account doesn't exist, create new one
    if (response["code"] == 400) and (response["error"] == "AccountNotFound"):
        time.sleep(0.2)
        
        request_object["CreateAccount"] = True
        
        response = post_request(url, headers=base_headers, jsonData=request_object)
        response = json.load(response)
    
    return response["data"]["SessionTicket"]

def get_server(ip_port_combo: str, xauth: str) -> dict:
    """
        Requests data from Playfab about the registered servers with matching IP/Port combinations
        
        Arguments:
            - ip_port_combo: The IP/Port combination of the server to get information about
            - xauth: The session token to be able to use the API
        
        Returns: The requested data or an error status object
    """
    
    url = f"{PLAYFAB_ASTRO_URL}/Client/GetCurrentGames?sdk={BASE_HEADERS['X-PlayFabSDK']}"
    
    # Only return servers that have a matching IP/Port combination
    request_object = {
        "TagFilter": {
            "Includes": [
                {"Data": {"gameId": ip_port_combo}}
            ]
        }
    }
    
    # Add XAuth header, such that we can use the API
    headers = BASE_HEADERS.copy()
    headers["X-Authorization"] = xauth
    
    try:
        response = post_request(url, headers=headers, jsonData=request_object)
        response = json.load(response)
        
        return dict(response)
    except Exception as e:
        raise PlayfabAPIError(f"Error while getting server from Playfab API: {str(e)}")

def deregister_server(lobby_id: str, xauth: str) -> dict:
    """
        Deregisters a server identified by the {lobbyID} from Playfab
        
        Arguments:
            - lobby_id: The Lobby ID identifying a registered server
            - xauth: The session token to be able to use the API
        
        Returns: The status of the operation or an object containing an error status
    """
    
    url = f"{PLAYFAB_ASTRO_URL}/Client/ExecuteCloudScript?sdk={BASE_HEADERS['X-PlayFabSDK']}"
    
    # Deregister Server with matching lobbyID
    request_object = {
        "FunctionName": "deregisterDedicatedServer",
        "FunctionParameter": {
            "lobbyId": lobby_id
        },
        "GeneratePlayStreamEvent": True
    }
    
    # Add XAuth header, such that we can use the API
    headers = BASE_HEADERS.copy()
    headers["X-Authorization"] = xauth
    
    try:
        response = post_request(url, headers=headers, jsonData=request_object)
        response = json.load(response)
        
        return dict(response)
    except Exception as e:
        raise PlayfabAPIError(f"Error while deregistering server from Playfab API: {str(e)}")

def heartbeat_server(server_data: dict, xauth: str, data_to_change: dict = None) -> dict:
    """
        Sends a heartbeat using the specified server data
        
        Arguments:
            - server_data: A server data dictionary containing the relevant information for the hearbeat (same as provided by get_server)
            - xauth: The session token to be able to use the API
            - data_to_change: Dictionary containing values that override values of the FunctionParameter dict of the request object
        
        Returns: The status of the operation or an object containing an error status
    """
    
    url = f"{PLAYFAB_ASTRO_URL}/Client/ExecuteCloudScript?sdk={BASE_HEADERS['X-PlayFabSDK']}"
    
    # Deregister Server with matching lobbyID
    request_object = {
            "FunctionName": "heartbeatDedicatedServer",
            "FunctionParameter": {
                "serverName": server_data['Tags']['serverName'],
                "buildVersion": server_data['Tags']['gameBuild'],
                "gameMode": server_data['GameMode'],
                "ipAddress": server_data['ServerIPV4Address'],
                "port": server_data['ServerPort'],
                "matchmakerBuild": server_data['BuildVersion'],
                "maxPlayers": server_data['Tags']['maxPlayers'],
                "numPlayers": str(len(server_data['PlayerUserIds'])),
                "lobbyId": server_data['LobbyID'],
                "publicSigningKey": server_data['Tags']['publicSigningKey'],
                "requiresPassword": server_data['Tags']['requiresPassword']
            },
            "GeneratePlayStreamEvent": True
        }
    
    # Add XAuth header, such that we can use the API
    headers = BASE_HEADERS.copy()
    headers["X-Authorization"] = xauth
    
    # Override values in FunctionParameter dict using values from `data_to_change`
    if data_to_change is not None:
        request_object['FunctionParameter'].update(data_to_change)
    
    try:
        response = post_request(url, headers=headers, jsonData=request_object)
        response = json.load(response)
        
        return dict(response)
    except Exception as e:
        raise PlayfabAPIError(f"Error while sending hearbeat to Playfab API: {str(e)}")
    