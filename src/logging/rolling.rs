/// Module: logging
/// File: rolling.rs
/// Author: JoeJoeTV
/// Description: Contains functionality to roll and compress existing log files and get the file nmame of a new one

use std::{
    fs::{create_dir_all, remove_file, OpenOptions}, io::{self, BufRead, BufReader, Write}, path::{Path, PathBuf, MAIN_SEPARATOR}
};
use flate2::{write::GzEncoder, Compression};
use jiff::Zoned;

/// Maximum number of allowed log files for one date.
const MAX_LOGFILE_NUMBER: i32 = 10000;

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