#
# File: astro/playfab.py
# Description: Fuctionality for interacting with the Playfab Astroneer API
# Note: This file is heavily based upon AstroAPI.py from [AstroLauncher](https://github.com/ricky-davis/AstroLauncher)
#

from ..utils.misc import GeneralError
import requests
import logging

LOGGER = logging.getLogger("Playfab")

BASE_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "X-PlayFabSDK": "UE4MKPL-1.49.201027",
    "User-Agent": "Astro/++UE4+Release-4.23-CL-0 Windows/10.0.19042.1.256.64bit"
}

PLAYFAB_ASTRO_TITLEID = "5EA1"
PLAYFAB_ASTRO_URL = f"https://{PLAYFAB_ASTRO_TITLEID}.playfabapi.com"

class PlayfabAPIError(General):
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
        response = requests.get(url).json()
        
        return response["Healthy"] == True
    except (requests.RequestException, KeyError) as e:
        raise PlayfabAPIError("Error while checking for Playfab API health") from e

def generate_xauth(server_guid: str) -> str:
    """
        Generates an X-Authorization token to use for further communication with Playfab
        
        Arguments:
            - server_guid: The GUID of the server, such that an account can be requested
        
        Returns: A session ticket to be used as X-Authorization in further requests
    """
    
    url = f"{PLAYFAB_ASTRO_URL}/Client/LoginWithCustomID"
    
    # First, check for existing account
    request_object = {
        "CreateAccount": False,
        "CustomId": server_guid,
        "TitleId": PLAYFAB_ASTRO_TITLEID
    }
    
    try:
        response = requests.post(url, headers=BASE_HEADERS, json=request_object, params={'sdk': BASE_HEADERS['X-PlayFabSDK']}).json()
        
        # If account doesn't exist, create new one
        if (response["code"] == 400) and (response["error"] == "AccountNotFound"):
            time.sleep(0.2)
            
            request_object["CreateAccount"] = True
            
            response = requests.post(url, headers=BASE_HEADERS, json=request_object, params={'sdk': BASE_HEADERS['X-PlayFabSDK']}).json()
        
        return response["data"]["SessionTicket"]
    except (requests.RequestException, KeyError) as e:
        raise PlayfabAPIError("Error while getting XAuth token") from e

def get_server(ip_port_combo: str, xauth: str) -> dict:
    """
        Requests data from Playfab about the registered servers with matching IP/Port combinations
        
        Arguments:
            - ip_port_combo: The IP/Port combination of the server to get information about
            - xauth: The session token to be able to use the API
        
        Returns: The requested data or an error status object
    """
    
    url = f"{PLAYFAB_ASTRO_URL}/Client/GetCurrentGames"
    
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
        response = requests.post(url, headers=headers, json=request_object, params={'sdk': BASE_HEADERS['X-PlayFabSDK']}).json()
        
        return dict(response)
    except requests.RequestException as e:
        raise PlayfabAPIError("Error while getting server from Playfab API") from e

def deregister_server(lobby_id: str, xauth: str) -> dict:
    """
        Deregisters a server identified by the {lobbyID} from Playfab
        
        Arguments:
            - lobby_id: The Lobby ID identifying a registered server
            - xauth: The session token to be able to use the API
        
        Returns: The status of the operation or an object containing an error status
    """
    
    url = f"{PLAYFAB_ASTRO_URL}/Client/ExecuteCloudScript"
    
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
        response = requests.post(url, headers=headers, json=request_object, params={'sdk': BASE_HEADERS['X-PlayFabSDK']}).json()
        
        return dict(response)
    except requests.RequestException as e:
        raise PlayfabAPIError("Error while deregistering server from Playfab API") from e

def heartbeat_server(server_data: dict, xauth: str, data_to_change: dict = None) -> dict:
    """
        Sends a heartbeat using the specified server data
        
        Arguments:
            - server_data: A server data dictionary containing the relevant information for the hearbeat (same as provided by get_server)
            - xauth: The session token to be able to use the API
            - data_to_change: Dictionary containing values that override values of the FunctionParameter dict of the request object
        
        Returns: The status of the operation or an object containing an error status
    """
    
    url = f"{PLAYFAB_ASTRO_URL}/Client/ExecuteCloudScript"
    
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
        response = requests.post(url, headers=headers, json=request_object, params={'sdk': BASE_HEADERS['X-PlayFabSDK']}).json()
        
        return dict(response)
    except requests.RequestException as e:
        raise PlayfabAPIError("Error while sending hearbeat to Playfab API") from e
    