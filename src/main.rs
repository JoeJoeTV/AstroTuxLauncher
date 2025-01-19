mod config;
mod logging;
mod notifications;
mod repl;
mod dedicatedserver;

use std::{env, process::exit, thread::{sleep, JoinHandle}, time::Duration};

use config::{Cli, Configuration, NotificationConfiguration};
use clap::{crate_version, Parser};
use log::{self, debug, info};
use logging::setup_logging;
use notifications::{DiscordNotificationThread, NtfyNotificationThread};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    /*
     * Setup 
     */

    // Parse CLI arguments
    let cli = Cli::parse();
    
    // Load configuration
    let config: Configuration = match Configuration::figment(&cli.config_path, &cli).extract() {
        Ok(c) => c,
        Err(e) => {
            println!("Configuration Error: {}", e);
            exit(1);
        },
    };

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

    // Register signal handler
    let (signal_sender, _signal_receiver) = flume::unbounded();

    ctrlc::set_handler(move || {
        signal_sender.send(()).unwrap()
    }).unwrap();

    // Start notification thread
    let notification_handle = match notification_thread {
        Some(notification_thread) => Some(notification_thread.start()),
        None => None,
    };

    /*
     * Start manager
     */

    info!(skip_notify=true; "AstroServerManager v{}", crate_version!());
    debug!(skip_notify=true; "Exe dir: {:?}", env::current_exe().unwrap().parent().unwrap().canonicalize().unwrap().display());

    debug!(skip_notify=true; "Configuration: {:#?}", config);

    /*
     * Stop manager
     */

    // Before exiting, stop notification thread
    if let (Some(notification_handle),Some(notification_sender)) = (notification_handle,notification_sender) {
        notification_sender.send(notifications::NotificationThreadMessage::Stop).unwrap();
        notification_handle.join().unwrap();
    }

    Ok(())
}
