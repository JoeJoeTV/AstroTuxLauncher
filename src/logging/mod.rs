mod rolling;

use fern::colors::{Color, ColoredLevelConfig};
use flume::Sender;
use jiff::Zoned;
use log::LevelFilter;
use std::path::Path;

use crate::notifications::{NotificationLevel, NotificationThreadMessage};

/// Name used as the log target for server events
pub const SERVER_EVENT_TARGET: &str = "event";

pub fn setup_logging(log_level: &LevelFilter, log_directory: &Path, log_file_level: &LevelFilter,
        notification_level: NotificationLevel, notification_sender: Option<Sender<NotificationThreadMessage>>) -> Result<(), fern::InitError> {
    let base_config = fern::Dispatch::new();

    let colors_line = ColoredLevelConfig::new()
        .error(Color::Red)
        .warn(Color::Yellow)
        .info(Color::White)
        .debug(Color::BrightBlack)
        .trace(Color::BrightBlack);

    let file_config = fern::Dispatch::new()
        .format(|out, message, record| {
            // [01.01.01/12:12:12] [target/info] message
            out.finish(format_args!(
                "[{datetime}] [{target}/{level}] {message}",
                datetime = Zoned::now().strftime("%d.%m.%y/%H:%M:%S"),
                target = record.target(),
                level = record.level(),
                message = message,
            ));
        })
        .level(log_file_level.clone())
        .chain(fern::log_file(rolling::roll_logfile("asm.log", log_directory)?)?);
    
    let console_config = fern::Dispatch::new()
        .format(move |out, message, record| {
            // [12:12:12] [target/info] message
            out.finish(format_args!(
                "[{time}] {line_color}[{target}/{level}] {message}\x1B[0m",
                line_color = format_args!(
                    "\x1B[{}m",
                    colors_line.get_color(&record.level()).to_fg_str()
                ),
                time = Zoned::now().strftime("%H:%M:%S"),
                target = record.target(),
                level = record.level(),
                message = message,
            ));
        })
        .level(log_level.clone())
        .chain(
            fern::Dispatch::new()
                .filter(|metadata| metadata.level() == LevelFilter::Error)
                .chain(std::io::stderr())
        )
        .chain(
            fern::Dispatch::new()
                .filter(|metadata| metadata.level() > LevelFilter::Error)
                .chain(std::io::stdout())
        );

    let mut log_config = base_config
        .chain(file_config)
        .chain(console_config);
    
    if let Some(notification_sender) = notification_sender {
        let notification_config = fern::Dispatch::new()
            .level(notification_level.into())
            .level_for(SERVER_EVENT_TARGET, LevelFilter::Info)
            .chain(fern::Output::call(move |record| {
                let kv = record.key_values();
    
                // If the log message is from a notification provides, we don't wan't to send it there again
                if let Some(v) = kv.get("skip_notify".into()) {
                    let skip_notify = v.to_bool().unwrap();
                    if skip_notify {
                        return;
                    }
                }
    
                let event_id = kv.get("event".into()).map(|v|v.to_string());
    
                notification_sender.send(NotificationThreadMessage::msg(
                    record.args().to_string(),
                    Zoned::now().timestamp(),
                    record.level(),
                    event_id)).unwrap();
            }));
        
            log_config = log_config.chain(notification_config);
    }

    log_config.apply()?;

    Ok(())
}