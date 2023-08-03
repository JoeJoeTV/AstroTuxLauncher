#
# This file is heavily based upon code from [AstroLauncher](https://github.com/ricky-davis/AstroLauncher)
#

import json
import urllib
import urllib.error
from urllib import request
import ssl
import time

def get_request(url, timeout=5):
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

def post_request(url, headers={}, jsonData={}, timeout=5):
    """
        Perform a POST request to {url} using the specified {headers} containing the specified {jsonData}.
        
        Arguments:
            - url: The URL to perform the request on
            - [headers]: A dictionary containing key-value pairs representing the headers to be used for the request and their values
            - [jsonData]: A dictionary containing JSON data to be sent as the content of the request
            - [timeout]: Timeout for the request
        
        Returns: The data response from the request or an HTTPError
    """
    
    req = request.Request(url)
    
    # Stringify JSON data
    if jsonData != {}:
        jsonString = json.dumps(jsonData).encode("utf-8")
        req.add_header("Content-Type", "application/json; charset=utf-8")
    else:
        jsonString = None
    
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
    except urllib.error.HTTPError as e:
        response = e
    
    return response
