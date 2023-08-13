"""
    Module containing utility methods to interact with, download from and update using Steam
"""

import tempfile
from urllib import request
from os import path
import zipfile
import shutil
import subprocess
import time

DEPOTDL_LATEST_ZIP_URL="https://github.com/SteamRE/DepotDownloader/releases/latest/download/DepotDownloader-linux-x64.zip"

def dl_depotdownloader(dest_dir, execname="depotdownloader"):
    """ Downloads the latest release of [depotdownloader](https://github.com/SteamRE/DepotDownloader) and saves it at {dlpath} under the name {execname} """
    
    if not path.isdir(dlpath):
        raise NotADirectoryError("Destination path does not point to a directory")
    
    # Create temporary directory to store downloaded zip at
    with tempfile.TemporaryDirectory() as tmpdir:
        # Download DepotDownloader release zip and save it in temporary directory
        zip_path, _ = request.urlretrieve(DEPOTDL_LATEST_ZIP_URL, filename=path.join(tmpdir, "depotdl.zip"))
        
        # Extract zip file into tmp dir
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)
        
        dlexec_path = path.join(tmpdir, "DepotDownloader")
        
        if not path.isfile(dlexec_path):
            raise FileNotFoundError("Executable not present after extraction")
        
        dest_path = path.join(dest_dir, execname)
        
        shutil.move(dlexec_path, dest_path)
    
    return dest_path

def update_app(exec_path, app, os, directory):
    """
        Updates a steam app using the provided DepotDownloader executable {exec}.
        
        Arguments:
            - exec_path: Path to the DepotDownloader executable
            - app: The id of the app to update
            - os: The OS to download the update for
            - directory: The directory to install the update in
        
        Returns: True, if the update process exited with a zero exit code and False if not
    """
    
    if not path.isfile(exec_path):
        raise FileNotFoundError("Executable path does not point to a file")
    
    cmd_args = [str(exec_path), "-app", str(app), "-os", str(os), "-dir", path.abspath(directory), "-validate"]
    
    updateproc = subprocess.Popen(cmd_args, creationflags=subprocess.DETACHED_PROCESS)
    
    # Wait until process is finished
    while updateproc.poll() is None:
        time.sleep(0.1)
    
    # Return boolean based on update process exit code
    return (updateproc.poll() == 0)