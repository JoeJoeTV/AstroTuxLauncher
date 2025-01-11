mod config;
mod logging;
mod notifications;
#[allow(dead_code)]
mod discord;

use std::{env, thread::{sleep, JoinHandle}, time::Duration};

use config::{Cli, Configuration, NotificationConfiguration};
use clap::{crate_version, Parser};
use log::{self, debug, info};
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

    // Create notification channel, if applicable
    let (notification_sender, notification_thread) = match &config.notifications {
        NotificationConfiguration::None => (None, None),
        NotificationConfiguration::Ntfy { name: _, level: _, emojis, topic, server_url, priorities } => {
            let t = NtfyNotificationThread::new(server_url.clone(), topic.clone(), emojis.clone(), priorities.clone())?;
            (Some(t.get_sender()), Some(t))
        },
        NotificationConfiguration::Discord { name: _, level: _, emojis, colors, webhook_url } => {
            let t = DiscordNotificationThread::new(webhook_url.clone(), emojis.clone(), colors.clone());
            (Some(t.get_sender()), Some(t))
        },
    };
    
    // Setup logging to console and file
    setup_logging(
        &config.manager.log_level,
        &config.manager.log_path,
        &config.manager.log_file_level,
        config.notifications.get_level(),
        notification_sender.clone()
    )?;

    let (signal_sender, signal_receiver) = flume::unbounded();

    ctrlc::set_handler(move || {
        signal_sender.send(()).unwrap()
    }).unwrap();

    info!(skip_notify=true; "AstroServerManager v{}", crate_version!());

    debug!(skip_notify=true; "Configuration: {:#?}", config);

    // Start notification thread
    let notification_handle = match notification_thread {
        Some(notification_thread) => Some(notification_thread.start()),
        None => None,
    };


    // Before exiting, stop notification thread
    if let (Some(notification_handle),Some(notification_sender)) = (notification_handle,notification_sender) {
        notification_sender.send(notifications::NotificationThreadMessage::Stop).unwrap();
        notification_handle.join().unwrap();
    }

    Ok(())
}
