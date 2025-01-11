use fern::colors::{Color, ColoredLevelConfig};
use flate2::{write::GzEncoder, Compression};
use flume::Sender;
use jiff::Zoned;
use log::LevelFilter;
use std::{
    fs::{create_dir_all, remove_file, OpenOptions}, io::{self, BufRead, BufReader, Write}, path::{Path, PathBuf, MAIN_SEPARATOR}
};

use crate::notifications::{NotificationLevel, NotificationThreadMessage};

/// Maximum number of allowed log files for one date.
const MAX_LOGFILE_NUMBER: i32 = 10000;
/// Name used as the log target for server events
pub const SERVER_EVENT_TARGET: &str = "event";

/// Select log file name using base name, the current date and an increasing number
/// and compress old log files using gzip
pub fn roll_logfile(base_filename: &str, log_directory: &Path) -> io::Result<PathBuf> {
    // Make sure the logs directory exists
    create_dir_all(log_directory)?;

    if base_filename.contains(MAIN_SEPARATOR) { return Err(io::Error::other("Base filename can't include directory separator!"))};

    let mut logfile_path = log_directory.join(base_filename);
    let base_stem = logfile_path.file_stem().unwrap().to_str().unwrap().to_owned();
    let base_ext = logfile_path.extension().unwrap().to_str().unwrap().to_owned();
    logfile_path.set_file_name(format!(
        "{}_{}.{}",
        logfile_path.file_stem().unwrap().to_str().unwrap(),
        Zoned::now().strftime("%Y-%m-%d"),
        logfile_path.extension().unwrap().to_str().unwrap(),
    ));

    let compressed_log_path = logfile_path.parent().unwrap()
        .join(logfile_path.file_name().unwrap().to_str().unwrap().to_owned() + ".gz");

    if logfile_path.exists() || compressed_log_path.exists() {
        // The "first" log file for the day already exists, so we need to check with the added number

        let mut i = 1;
        let full_stem = logfile_path.file_stem().unwrap().to_str().unwrap().to_owned();
        loop {
            if i > MAX_LOGFILE_NUMBER {
                return Err(io::Error::other(format!("There are over {} log files for the current day, consider looking for why that is!", MAX_LOGFILE_NUMBER)));
            }
            logfile_path.set_file_name(format!(
                "{}.{}.{}",
                full_stem,
                i,
                logfile_path.extension().unwrap().to_str().unwrap(),
            ));

            let compressed_log_path = logfile_path.parent().unwrap()
                .join(logfile_path.file_name().unwrap().to_str().unwrap().to_owned() + ".gz");

            if !logfile_path.exists() && !compressed_log_path.exists() {
                break;
            }

            i += 1;
        }
    }

    // Now, gzip existing log files, which are not alreaddy gzipped
    log_directory.read_dir()?.filter_map(|e| {
        match e {
            Ok(entry) => {
                let filename = entry.file_name();
                if let Ok(metadata) = entry.metadata() {
                    if metadata.is_file() && entry.path().extension()?.to_str()? == base_ext && filename.to_str().to_owned().unwrap().starts_with(&base_stem){
                        return Some(entry.path())
                    }
                }
                return None
            }
            Err(_) => return None
        };
    }).try_for_each(|p| {
        let mut compressed_path = p.clone();
        compressed_path.set_file_name(p.file_name().unwrap().to_str().unwrap().to_owned() + ".gz");

        // If the compressed file already exists, delete first and then re-compress it
        if compressed_path.exists() {
            remove_file(&compressed_path)?;
        }

        let mut log_reader = {
            let curr_log_file = OpenOptions::new().read(true).open(&p)?;
            BufReader::new(curr_log_file)
        };

        let compressed_file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(compressed_path)?;

        let mut compressed_encoder = GzEncoder::new(compressed_file, Compression::best());

        // Compress content
        loop {
            let buf = log_reader.fill_buf()?;
            let len = buf.len();

            if len == 0 {
                break;
            }

            compressed_encoder.write_all(buf)?;
            log_reader.consume(len);
        }

        compressed_encoder.flush()?;

        // Drop file reader before deleting file
        drop(log_reader);

        // Remove uncompressed original log file
        remove_file(p)?;

        Ok::<(), io::Error>(())
    })?;

    // We always return a new file for every time the function is run
    Ok(logfile_path.clone())
}

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
        .chain(fern::log_file(roll_logfile("asm.log", log_directory)?)?);
    
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