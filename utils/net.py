#
# This file is heavily based upon code from [AstroLauncher](https://github.com/ricky-davis/AstroLauncher)
#

import json
import urllib
import urllib.error
from urllib import request
import ssl
import time
import socket
import secrets
import threading
import logging
from contextlib import contextmanager

import traceback

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
    except urllib.error.HTTPError as e:
        response = e
    
    return response

def get_public_ip():
    logging.debug("Getting IP from remote service")
    url = "https://api.ipify.org?format=json"
    x = json.load(get_request(url))
    logging.debug(f"Received data: {json.dumps(x)}")
    return x['ip']

def valid_ip(address):
    try:
        socket.inet_aton(address)
        return True
    except:
        return False


@contextmanager
def tcp_socket_scope(ip, port):
    """ Creates TCP socket and closes it. For use in combination with with statement """
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((ip, int(port)))
        yield s
    except:
        pass
    finally:
        s.close()


def secret_socket_client(ip, port, secret, tcp):
    """ Sends {secret} to {ip}:{port} over TCP if {tcp} is set and UDP if not """
    try:
        if tcp:
            with tcp_socket_scope(ip, port) as s:
                s.sendall(secret)
        else:
            time.sleep(2)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(secret, (ip, port))
    except Exception as e:
        pass

def secret_socket_server(port, secret, tcp):
    """
        Tries to receive data on the given {port} and compares it to the given {secret}.
        If the data matches the secret, return True, else return False.
        {tcp} indicates if TCP or UDP should be used.
    """
    try:
        # Create correct socket
        if tcp:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        server_socket.settimeout(10)
        
        # Bind to public host
        server_socket.bind(("0.0.0.0", port))
        
        # Become server socket
        if tcp:
            server_socket.listen(1)
        
        while True:
            # Accept connections
            connection = None
            
            if tcp:
                connection, _client_address = server_socket.accept()
            
            # Receive and check data
            while True:
                if tcp:
                    data = connection.recv(32)
                else:
                    data = server_socket.recv(32)
                
                # If data matches, were finished
                if data == secret:
                    logging.debug("Received Data matches expected secret")
                    
                    if tcp:
                        connection.close()
                    
                    return True
                else:
                    logging.debug(f"Received Data ({str(data)}) doesn't match expected secret ({str(secret)})")
                    
                    return False
    except Exception as e:
        logging.error(f"Error during receiving: {str(e)}")
        logging.error(traceback.format_exc())
        return False
    finally:
        server_socket.close()

def net_test_local(ip, port, tcp):
    """
        Test, if this application is reachable from the local network over TCP if {tcp} is set and UDP is not
    """
    
    secret_phrase = secrets.token_hex(16).encode()
    
    # Send secret phrase to public IP
    send_thread = threading.Thread(target=secret_socket_client, args=(ip, port, secret_phrase, tcp))
    send_thread.start()
    
    time.sleep(0.01)
    
    # Try to receive secret phrase and return success
    return secret_socket_server(port, secret_phrase, tcp)

def nonlocal_socket_server(port):
    """
        Tries to receive data on the given {port} via UDP and if it matches the expected bytes, answers with message
    """
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        server_socket.settimeout(10)
        
        # Bind to public host
        server_socket.bind(("0.0.0.0", port))
        
        while True:
            # Receive data from socket
            data, address = server_socket.recvfrom(32)
            
            # kept from AstroLauncher. Data sent by ServerCheck site?
            # Expected Data in bytes
            expected_bytes = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08])
            
            if data == expected_bytes:
                server_socket.sendto(b"Hello from AstroTuxLauncher", address)
                return True
            else:
                return False
    except:
        return False
    finally:
        server_socket.close()

def net_test_nonlocal(ip, port):
    """ Test connection to host with {ip} on {port} via UDP from outside of the local network by using external service """
    # Setup receive thread to repsond to outside message
    server_thread = threading.Thread(target=nonlocal_socket_server, args=(port,))
    server_thread.start()
    
    # Use external service to test connection
    try:
        resp = post_request(f"https://servercheck.spycibot.com/api?ip_port={ip}:{port}", timeout=10)
        json_resp = json.load(resp)
    except:
        logging.warning("Connection to external service failed")
        logging.warning("Unable to verify connectivity from outside local network")
        logging.debug(f"Response from external Service: {str(resp)}")
        return False
    
    
    return json_resp["Server"]