mod config;
mod logging;
mod notifications;
#[allow(dead_code)]
mod discord;

use std::{env, thread::sleep, time::Duration};

use config::{Cli, Configuration};
use clap::Parser;
use log::{self, info};
use logging::setup_logging;
use notifications::{DiscordNotificationThread, NtfyNotificationThread};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("Hello, world!");
    println!("Exe dir: {:?}", env::current_exe().unwrap().parent().unwrap().canonicalize().unwrap().display());

    // Parse CLI arguments
    let cli = Cli::parse();
    
    // Load configuration
    let config: Configuration = Configuration::figment(&cli.config_path, &cli).extract()?;

    println!("Configuration: {:#?}", config);

    let notification_thread = match &config.notifications {
        config::NotificationConfiguration::None => None,
        config::NotificationConfiguration::Ntfy {name: _, level: _, emojis, topic, server_url, priorities } => 
            Some(NtfyNotificationThread::new(server_url.clone(), topic.clone(), emojis.clone(), priorities.clone())?),
        config::NotificationConfiguration::Discord { name: _, level: _, emojis, webhook_url, colors } => 
            Some(DiscordNotificationThread::new(webhook_url.clone(), emojis.clone(), colors.clone())),
    };
    
    // Setup logging to console and file
    setup_logging(
        &config.manager.log_level,
        &config.manager.log_path,
        config.notifications.get_level(),
        notification_thread.as_ref().map(|t|t.as_ref().get_sender())
    )?;

    if let Some(notification_thread) = notification_thread {
        notification_thread.start();
    }

    info!(env!("CARGO_PKG_VERSION"));

    sleep(Duration::from_secs(4));

    Ok(())
}
