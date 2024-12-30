mod config;
mod logging;

use std::env;

use config::{Cli, Configuration};
use clap::Parser;
use log::{debug, info, trace, error, warn};
use logging::setup_logging;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("Hello, world!");
    println!("Exe dir: {:?}", env::current_exe().unwrap().parent().unwrap().canonicalize().unwrap().display());

    // Parse CLI arguments
    let cli = Cli::parse();
    
    // Load configuration
    let config: Configuration = Configuration::figment(&cli.config_path, &cli).extract()?;

    // Setup logging to console and file
    setup_logging(&config.manager.log_level, &config.manager.log_path)?;

    println!("Configuration: {:#?}", config);

    Ok(())
}
