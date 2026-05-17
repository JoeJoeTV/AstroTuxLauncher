# AstroTuxLauncher


Launcher and management utility for running an Astroneer Dedicated Server on Linux using WINE.

## Prerequisites

- **Python 3.9+** (Tested with 3.9.5, 3.10.12, 3.11.0rc1, 3.12.3; Please report compatibility problems)
- Python packages in `requirements.txt`
- Wine
- A public IP or something like playit.gg

## How to use

### Option 1: Use pre-built executable

1. Create a new folder to house AstroTuxLauncher and the dedicated server.
2. Download the `AstroTuxLauncher` executable for the latest release from the [releases page](https://github.com/JoeJoeTV/AstroTuxLauncher/releases) and put it into the created folder.
3. Open a terminal in the created folder and make sure the `AstroTuxLauncher` file is executable.
4. Install the Astroneer Dedicated Server into default subfolder by executing the following
    ```sh
    ./AstroTuxLauncher install
    ```
5. [Optional] Change launcher configuration in `launcher.toml` (Can be changed later)
6. Start the installed Astroneer Dedicated Server for the first time:
    ```sh
    ./AstroTuxLauncher start
    ```
7. Done! You can stop the server by entering the `shutdown` command or pressing <kbd>Ctrl</kbd>+<kbd>C</kbd>

### Option 2: Use python with the source code

1. Clone the repository
    ```sh
    git clone https://github.com/JoeJoeTV/AstroTuxLauncher
    ```
2. Change into repository directory
    ```sh
    cd AstroTuxLauncher
    ```
3. Install required python modules
    ```sh
    pip install -r requirements.txt
    ```
4. Install Astroneer Dedicated Server into default directory
    ```sh
    python3 AstroTuxLauncher.py install
    ```
5. [Optional] Change launcher configuration in `launcher.toml` (Can be changed later)
6. Start installed Astroneer Dedicated Server
    ```sh
    python3 AstroTuxLauncher.py start
    ```

## Updating

If a new version of AstroTuxLauncher has been released and git was used to clone the repository, an update can simply be performed by using git:

```sh
git pull
```

## Notice about Encryption

Currently, the Launcher disables encryption for the Astroneer Dedicated Server by default. This is required as the Server doesn't work with encryption enabled running under WINE.

**If the Dedicated Server has encryption disabled, every client that wants to connect also has to disable encryption**

## Launcher Configuration

The launcher configuration will be stored in `launcher.toml` in the same folder as `AstroTuxLauncher.py`by default with the following options:
```toml
[launcher]

# (Boolean) Wether the Launcher should automatically update/install the Astroneer Dedicated Server at start
AutoUpdateServer = true

# (Boolean) Wether to check the network configuration for any problems
CheckNetwork = true

# (Boolean) Wether to always overwrite the PublicIP field of the
# Dedicated Server configuration file with the public IP gotten from an external service
OverwritePublicIP = false

# (Boolean) Wether to output debug messages (Warning: Highly increased output)
LogDebugMessages = false

# (Path as String) Relative or absolute path to the directory where the Astroneer Dedicated server should reside
AstroServerPath = "AstroneerServer"

# (Optional, Path as String) Relative or absolute path to the wine executable to override system binary
OverrideWinePath = # Not set by default

# (Path as String) Relative or absolute path to the directory where the WINE prefix
# used for running the server should reside
WinePrefixPath = "winepfx"

# The time (in seconds) that Wine will wait before closing out during Prefix check and creation
# Default value: 30
WineBootTimeout = 30

# (Path as String) Relative or absolute path to the directory where the log files should reside
LogPath = "logs"

# (Integer) Interval for connecting to the Playfab API in seconds
PlayfabAPIInterval = 2

# (Float) Interval for asking the Dedicated Server about it's status in seconds 
ServerStatusInterval = 3.0

# (Boolean) Wether to force disable encryption for the Dedicated Server
DisableEncryption = true

# (Optional, Path as String) Path to executable of a wrapper for Wine (e.g. Box64)
WrapperPath = # Not set by default


# Settings related to sending notifications to external services
[launcher.notifications]

# (""(None)/"discord"/"ntfy") What service to send notifications to
method = "ntfy"

# (String) Name of the server to use in notifications
name = "Astro DS"

# (List of String) Event types that should be sent using the external notification method (By default all event types)
EventWhitelist = ["message", "start", "registered", "shutdown", "crash", "player_join", "player_leave", "command", "save", "savegame_change"]


# (Optional) Settings specific to Discord (Only required, if method is "discord")
[launcher.notifications.discord]

# (URL as String) URL of the webhook to send notifications to
webhookURL = # Not set by default


# Settings specific to ntfy (Only required, if method is "ntfy")
[launcher.notifications.ntfy]

# (String) The topic to send notifications to 
topic = # Not set by default

# (URL as String) URL of the ntfy server to use for sending notifications
serverURL = "https://ntfy.sh"

# Settings related to sending status updates to an endpoint (currently mostly just Uptime Kuma using the 'Push' monitor type)
[launcher.status]

# (Boolean) Wether to send status updates at all
SendStatus = false

# (Integer) The interval in seconds to send status updates at, if the status doesn't change in-between
Interval = 120

# (URL as String) The endpoint to send the status update to as a GET request with parameters
EndpointURL = ""
```


## Credits

- Mostly based on [AstroLauncher](https://github.com/ricky-davis/AstroLauncher)
- Spyci and Konsti on the Astroneer Discord Server for helping clarify details about how the Dedicated Server works
