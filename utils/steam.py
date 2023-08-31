"""
    Module containing utility methods to interact with, download from and update using Steam
"""

import tempfile
from urllib import request
from os import path
import os
import zipfile
import shutil
import subprocess
import time
import logging
from utils.interface import run_proc_with_logging, safeformat, DOTS_SPINNER
from alive_progress import alive_bar
from utils.misc import CONTROL_CODES_SUPPORTED

DEPOTDL_LATEST_ZIP_URL="https://github.com/SteamRE/DepotDownloader/releases/latest/download/DepotDownloader-linux-x64.zip"

LOGGER = logging.getLogger("Steam")

def reporthook(blocks_done, block_size, file_size):
    size_trans = blocks_done * block_size
    trans_percentage = (size_trans / file_size) * 100
    
    LOGGER.info(f"[Download] {trans_percentage}%")

class FileDownloader:
    """ Downloads a file while logging the percentage of the download """
    
    MSG_FORMAT="[Download] {percentage}%"
    
    def __init__(self, url, filename=None, msg_format=MSG_FORMAT, log_level=logging.INFO, percent_mod=1):
        self.url = url
        self.filename = filename
        self.msg_format = msg_format
        self.log_level = log_level
        self.percent_mod = percent_mod
        self.alive_bar = None
        
        self._prev_percentage = -1
    
    def _reporthook(self, blocks_done, block_size, file_size):
        size_trans = blocks_done * block_size
        fraction = (size_trans / file_size)
        
        # If an alive-progressbar was passed, update it with percentage
        if self.alive_bar:
            self.alive_bar(min(fraction, 1))
        
        percentage = (round(fraction * 100) // self.percent_mod) * self.percent_mod
        
        if percentage > 100:
            LOGGER.debug(f"Download percentage overshoot: {percentage}%")
        
        if percentage != self._prev_percentage:
            LOGGER.log(self.log_level, safeformat(self.msg_format, percentage=percentage))
            self._prev_percentage = percentage
    
    def download(self, alive_bar=None):
        self.alive_bar = alive_bar
        
        if self.filename:
            file_path, http_msg = request.urlretrieve(self.url, filename=self.filename, reporthook=self._reporthook)
        else:
            file_path, http_msg = request.urlretrieve(self.url, reporthook=self._reporthook)
        
        return file_path, http_msg

def dl_depotdownloader(dest_dir, execname="depotdownloader"):
    """ Downloads the latest release of [depotdownloader](https://github.com/SteamRE/DepotDownloader) and saves it at {dlpath} under the name {execname} """
    
    if not path.isdir(dest_dir):
        raise NotADirectoryError("Destination path does not point to a directory")
    
    # Create temporary directory to store downloaded zip at
    with tempfile.TemporaryDirectory() as tmpdir:
        # Download DepotDownloader release zip and save it in temporary directory
        dl = FileDownloader(DEPOTDL_LATEST_ZIP_URL, filename=path.join(tmpdir, "depotdl.zip"), log_level=logging.DEBUG, percent_mod=5)
        
        LOGGER.debug(f"Downloading '{DEPOTDL_LATEST_ZIP_URL}' to '{path.join(tmpdir, 'depotdl.zip')}'")
        
        start_time = time.time()
        
        with alive_bar(title="Downloading DepotDownloader", spinner=DOTS_SPINNER, bar="smooth", manual=True, receipt=True, enrich_print=False, force_tty=CONTROL_CODES_SUPPORTED) as bar:
            zip_path, _ = dl.download(bar)
        
        # Extract zip file into tmp dir
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)
        
        dlexec_path = path.join(tmpdir, "DepotDownloader")
        
        if not path.isfile(dlexec_path):
            raise FileNotFoundError("Executable not present after extraction")
        
        dest_path = path.join(dest_dir, execname)
        
        shutil.move(dlexec_path, dest_path)
        
        # Make file executable
        os.chmod(dest_path, 0o775)
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        LOGGER.info(f"Finished downloading DepotDownloader in {round(elapsed, 2)} seconds")
    
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
    
    LOGGER.debug(f"Executing DepotDownloader command: {' '.join(cmd_args)}")
    
    start_time = time.time()
    
    # Run update command, log output and wait until it is finished
    with alive_bar(title=f"Updating app {app}", spinner=DOTS_SPINNER, bar=None, receipt=True, enrich_print=False, monitor=False, stats=False, force_tty=CONTROL_CODES_SUPPORTED) as bar:
        proc_res = run_proc_with_logging(cmd_args, "DepotDL", level=logging.DEBUG, alive_bar=bar)
    
    end_time = time.time()
    elapsed = end_time - start_time

    success = (proc_res == 0)
    
    if success:
        LOGGER.info(f"Finished updating app {app} in {round(elapsed, 2)} seconds")
    
    # Return boolean based on update process exit code
    return success