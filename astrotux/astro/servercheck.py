#
# File: astro/servercheck.py
# Description: Fuctionality for interacting with the server checker API
#

from ..utils.misc import GeneralError
import requests
import logging

LOGGER = logging.getLogger("Servercheck")

SERVERCHECK_API_BASE_URL = "https://astroneermods.space/tools/servercheck/api"

class ServercheckAPIError(General):
    def __init__(self, message="An error occured while interacting with the Server checker API"):
        self.message = message
        super().__init__(self.message)

def get_stats() -> dict:
    """
        Retrieves the stats from the server checker including the latest version
        
        Returns: A dict containing the stats
    """
    
    url = f"{SERVERCHECK_API_BASE_URL}/stats"
    
    try:
        response = requests.get(url)
        
        # If we get status code 400, the API returns an error message
        if response.status_code == 400:
            response = response.json()
            raise ServercheckAPIError(response["message"])
        
        # If error status code returned, raise exception first, so its not reported as a JSONDecodeError
        response.raise_for_status()
        response = response.json()
        
        return response["stats"]
    except (requests.RequestException, KeyError) as e:
        raise ServercheckAPIError("Error while getting stats from the server checker API") from e

def check_server(ip_port: str) -> dict:
    """
        Checks the server at the given IP and port using the server checker API
        
        Arguments:
            - ip_port: Combination of IP and Port ({IP}:{Port}) pointing to the server to check
        
        Returns: A dict containing the satatus of the server
    """
    
    url = f"{SERVERCHECK_API_BASE_URL}/check"
    
    try:
        response = requests.get(url, params={"url": ip_port})
        
        # If we get status code 400, the API returns an error message
        if response.status_code == 400:
            response = response.json()
            raise ServercheckAPIError(response["message"])
        
        # If error status code returned, raise exception first, so its not reported as a JSONDecodeError
        response.raise_for_status()
        response = response.json()
        
        return response["server"]
    except (requests.RequestException, KeyError) as e:
        raise ServercheckAPIError("Error while getting the server status from the server checker API") from e
