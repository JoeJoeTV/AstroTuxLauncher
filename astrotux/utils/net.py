#
# File: utils/net.py
# Description: Fuctionality related to networking
# Note: This file is based upon [AstroLauncher](https://github.com/ricky-davis/AstroLauncher)
#

import json, ssl
from urllib import request
from urllib.error import HTTPError
from http.client import HTTPResponse

def get_request(url: str, timeout: int = 5) -> HTTPResponse:
    """
        Perform a GET request to {url} while using system spefified proxies and SSL.
    
        Arguments:
            - url: The URL to perform the request on
            - [timeout]: Timeout for request
        
        Returns: The data response from the request
    """
    
    # Install handler for using specified proxies
    proxy_handler = request.ProxyHandler(request.getproxies())
    opener = request.build_opener(proxy_handler)
    request.install_opener(opener)
    
    sslcontext = ssl.SSLContext()
    
    # Perform GET request to url
    response = request.urlopen(url, timeout=timeout, context=sslcontext)
    
    return response

def post_request(url: str, headers: dict = {}, json_data: dict = {}, timeout: int = 5):
    """
        Perform a POST request to {url} using the specified {headers} containing the specified {jsonData}.
        
        Arguments:
            - url: The URL to perform the request on
            - [headers]: A dictionary containing key-value pairs representing the headers to be used for the request and their values
            - [json_data]: A dictionary containing JSON data to be sent as the content of the request
            - [timeout]: Timeout for the request
        
        Returns: The data response from the request or an HTTPError
    """
    
    req = request.Request(url)
    
    # Stringify JSON data
    if json_data != {}:
        jsonString = json.dumps(json_data).encode("utf-8")
        req.add_header("Content-Type", "application/json; charset=utf-8")
    else:
        jsonString = b""
    
    for header, value in headers.items():
        req.add_header(header, value)
    
    # Install handler for using specified proxies
    proxy_handler = request.ProxyHandler(request.getproxies())
    opener = request.build_opener(proxy_handler)
    request.install_opener(opener)
    
    sslcontext = ssl.SSLContext()
    
    # Try performing request and if error is caught, return it
    try:
        response = request.urlopen(req, data=jsonString, timeout=timeout, context=sslcontext)
    except HTTPError as e:
        response = e
    
    return response