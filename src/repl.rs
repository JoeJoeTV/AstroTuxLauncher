/// File: repl.rs
/// Author: JoeJoeTV
/// Description: Contains the REPL interface for the server commands

use clap::{Args, Parser, Subcommand, ValueEnum};
use log::debug;
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize, Parser)]
#[command(multicall = true, disable_help_flag = true)]
pub struct LocalRepl {
    #[command(subcommand)]
    pub command: LocalCommand,
}

#[derive(Debug, Serialize, Deserialize, Subcommand)]
pub enum LocalCommand {
    /// Shuts down the dedicated server and exits the manager
    #[command(visible_alias = "exit")]
    Shutdown,
    /// Restarts the server without quitting the manager
    Restart,
    #[command(flatten)]
    Common(CommonCommand),
    
}

#[derive(Debug, Serialize, Deserialize, Parser)]
#[command(multicall = true, disable_help_flag = true)]
pub struct RemoteRepl {
    #[command(subcommand)]
    pub command: RemoteCommand,
}

#[derive(Debug, Serialize, Deserialize, Subcommand)]
pub enum RemoteCommand {
    /// Disconnects from the remote server and exits the manager
    #[command(visible_alias = "exit")]
    Disconnect,
    #[command(flatten)]
    Common(CommonCommand),
    
}

#[derive(Debug, Serialize, Deserialize, Subcommand)]
pub enum CommonCommand {
    /// Prints information about the dedicated server
    Info,
    /// Allows kicking players from the dedicated server
    Kick(KickCommand),
    /// Allows managing the whitelist of the dedicated server
    #[command(subcommand)]
    Whitelist(WhitelistCommand),
    /// Lists players currently connected to the server
    List(ListCommand),
    /// Allows working with the savegames on the server
    #[command(subcommand)]
    Savegame(SavegameCommand),
    /// Allows showing and modifying player's categories
    #[command(subcommand)]
    Player(PlayerCommand),
}

#[derive(Debug, Serialize, Deserialize, Args)]
pub struct KickCommand {
    /// The GUID or name of the player to kick
    player: String,
}

#[derive(Debug, Serialize, Deserialize, Subcommand)]
pub enum WhitelistCommand {
    /// Enabled the whitelist
    Enable,
    /// Disabled the whitelist
    Disable,
    /// Reports the current status of the whitelist
    Status,
}

#[derive(Debug, Serialize, Deserialize, Copy, Clone, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
pub enum ListCategory {
    /// List all players
    All,
    /// List only players, which have been put on the whitelist
    Whitelisted,
    /// List only players, which have been put on the blacklist 
    Blacklisted,
    /// List only players, which have the 'Unlisted' category
    Unlisted,
    /// List players which are administrators
    Admin,
    /// List the owner (is limited to a single player)
    Owner,
}

#[derive(Debug, Serialize, Deserialize, Args)]
pub struct ListCommand {
    /// The category of which players should be listed
    #[arg(value_enum)]
    category: ListCategory,
}

#[derive(Debug, Serialize, Deserialize, Subcommand)]
pub enum SavegameCommand {
    /// Load an existing savegame
    Load {
        /// The name of the savegame to load
        save_name: String,
    },
    /// Save the currently loaded savegame
    Save {
        /// The name to save the savegame as
        save_name: Option<String>,
    },
    /// Creata a new savegame
    New {
        /// The name to give the newly created savegame
        save_name: Option<String>,
    },
    /// List all available savegames
    List,
}


#[derive(Debug, Serialize, Deserialize, Copy, Clone, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
pub enum PlayerCategory {
    /// The player is whitelisted
    Whitelisted,
    /// The player is blacklisted
    Blacklisted,
    /// The player does not have any special category
    Unlisted,
    /// The player is an administrator
    Admin,
}


#[derive(Debug, Serialize, Deserialize, Subcommand)]
pub enum PlayerCommand {
    Set {
        /// The GUID or name of the player whose category to modify
        player: String,
        #[arg(value_enum)]
        category: PlayerCategory,
    },
    Get {
        /// The GUID or name of the player whose category to show
        player: String,
    },
}