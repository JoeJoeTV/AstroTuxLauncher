use std::{collections::HashMap, net::Ipv4Addr, path::PathBuf};

use clap::{Parser, Args, Subcommand};
use figment::{providers::{Env, Format, Serialized, Toml}, Figment};
use hex_color::HexColor;
use log::LevelFilter;
use serde::{Deserialize, Serialize};
use better_debug::BetterDebug;
use url::Url;
use crate::notifications::{NotificationLevel, NtfyPriority};

/*
 * Helper functions and types
 */

fn hide_ipv4_partially(server_cfg: &ServerConfiguration) -> Option<String> {
    Some(format!("{}.<redacted>", server_cfg.public_ip.to_owned().octets()[0]))
}

/*
 * CLI Configuration
 */

#[derive(Parser, Debug)]
#[command(name = "AstroServerManager")]
#[command(version, about = "A server manager for the Astroneer Dedicated Server", long_about = None)]
pub struct Cli {
    /// Path to the AstroServerManager configuration file
    #[arg(long = "config_path", short = 'c', default_value = "config.toml", global = true)]
    pub config_path: PathBuf,
    #[command(subcommand)]
    pub command: CliCommands,
    #[command(flatten, next_help_heading = "Configuration Options")]
    pub configuration: CliConfiguration
}

#[derive(Subcommand, Debug)]
pub enum CliCommands {
    /// Install/Update the dedicated server without explicitly checking, if a newer version exixts 
    #[command(visible_alias = "install",name = "update")]
    Update,
    /// Start the dedicated server
    #[command(name = "run")]
    Run,
    /// Connect to a running dedicated server via the console port
    #[command(name = "connect")]
    Connect(ConnectArgs),
}

#[derive(Args, Debug, Serialize, Deserialize)]
pub struct ConnectArgs {
    /// The IPv4 address of the host running the dedicated server to connect to
    pub host: Ipv4Addr,
    /// The console port of the dedicated server to connect to
    pub port: u16,
}

// NOTE: When updating the normal configuration, the cli configuration also has to be changed and vice versa 

#[derive(Args, Debug, Serialize, Deserialize)]
pub struct CliConfiguration {
    #[command(flatten)]
    #[serde(skip_serializing_if = "Option::is_none")]
    pub manager: Option<CliManagerConfiguration>,

    #[command(flatten)]
    #[serde(skip_serializing_if = "Option::is_none")]
    pub server: Option<CliServerConfiguration>,
}

#[derive(Args, Debug, Serialize, Deserialize)]
pub struct CliManagerConfiguration {
    #[arg(long, global = true)]
    #[serde(skip_serializing_if = "Option::is_none")]
    pub log_path: Option<PathBuf>,

    #[arg(long, global = true)]
    #[serde(skip_serializing_if = "Option::is_none")]
    pub log_level: Option<LevelFilter>,
}

#[derive(Args, Debug, Serialize, Deserialize)]
/// Configuration for the dedicated server
pub struct CliServerConfiguration {
    #[arg(long, global = true)]
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ds_path: Option<PathBuf>,
}

/*
 * General Configuration (cli, config file, env, etc.)
 * NOTE: (basically) same as CliConfiguration and related structs, but without Option and clap-related annotations
 */

#[derive(BetterDebug, Serialize, Deserialize)]
pub struct Configuration {
    pub manager: ManagerConfiguration,
    pub server: ServerConfiguration,
    //#[better_debug(secret)]
    pub notifications: NotificationConfiguration,
}

impl Configuration {
    pub fn figment(config_path: &PathBuf, cli: &Cli) -> Figment {
        let default_config: &str = include_str!("config.default.toml");
        const ENV_PREFIX: &str = "ASM_";
        let cli_config = &cli.configuration;
        
        if config_path.exists() && config_path.is_file() {
            Figment::new()
                .merge(Toml::string(default_config))
                .merge(Toml::file_exact(config_path))
                .merge(Env::prefixed(ENV_PREFIX))
                .merge(Serialized::defaults(cli_config))
        } else {
            Figment::new()
                .merge(Toml::string(default_config))
                .merge(Env::prefixed(ENV_PREFIX))
                .merge(Serialized::defaults(cli_config))
        }
    }
}

#[derive(Debug, Serialize, Deserialize)]
/// Configuration for the Manager itself
pub struct ManagerConfiguration {
    pub log_path: PathBuf,
    pub log_level: LevelFilter,
    pub log_file_level: LevelFilter,
}

#[derive(BetterDebug, Serialize, Deserialize)]
/// Configuration for the dedicated server
pub struct ServerConfiguration {
    pub ds_path: PathBuf,
    #[better_debug(cust_formatter = "hide_ipv4_partially")]
    pub public_ip: Ipv4Addr,
}


#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type")]
#[serde(rename_all(serialize = "lowercase", deserialize = "lowercase"))]
/// Configuration for notifications
pub enum NotificationConfiguration {
    /// Specifies that no notifications should be sent
    None,
    /// Specifies to send notifications to an ntfy topic  
    Ntfy {
        name: String,
        level: NotificationLevel,
        emojis: HashMap<String, String>,
        topic: String,
        server_url: Url,
        priorities: HashMap<String, NtfyPriority>,
    },
    /// Specifies to send notifications to a discord webhook
    Discord {
        name: String,
        level: NotificationLevel,
        emojis: HashMap<String, String>,
        colors: HashMap<String, HexColor>,
        webhook_url: Url,
    },
}

impl NotificationConfiguration {
    pub fn get_level(&self) -> NotificationLevel {
        match self {
            Self::None => NotificationLevel::Server,
            Self::Ntfy { level, ..} => *level,
            Self::Discord { level, .. } => *level,
        }
    }
}