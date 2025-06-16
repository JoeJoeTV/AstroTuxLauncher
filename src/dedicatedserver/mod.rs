use std::{fs::File, io::{self, BufRead}, path::{Path, MAIN_SEPARATOR}};

use anyhow::{anyhow, Context};
use const_format::concatcp;
use log::{debug, error};
use regex::{Captures, Regex};


#[derive(Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct BuildVersion(pub i16, pub i16, pub i16, pub i16);

#[derive(Debug)]
pub struct InstallInfo {
    pub present: bool,
    pub build_version: Option<BuildVersion>,
}

impl Default for InstallInfo {
    fn default() -> Self {
        Self {
            present: false,
            build_version: None,
        }
    }
}


/// Relative path to the server executable
pub const DS_EXECUTABLE_PATH: &str = concatcp!("Astro",MAIN_SEPARATOR,"Binaries",MAIN_SEPARATOR,"Win64",MAIN_SEPARATOR,"AstroServer-Win64-Shipping.exe");
/// Relative path to the server wrapper executable
pub const DS_WRAPPER_PATH: &str = "AstroServer.exe";
/// Relative path to the build version file
pub const DS_BUILD_VERSION_PATH: &str = "build.version";

/// Tries reading the build version from the given file
fn parse_build_version_file(path: &Path) -> anyhow::Result<BuildVersion> {
    let file = File::open(path).context("Could not open build version file")?;
    let mut line: String = String::default();
    io::BufReader::new(file).read_line(&mut line).context("Could not read build version file contents")?;

    let re = Regex::new(r"^(\d+)\.(\d+)\.(\d+)\.(\d+) .*").context("Could not parse build version file contents")?;

    let captures: Captures<'_> = re.captures(&line).ok_or(anyhow!("Could not parse build version string: {:?}", line))?;

    Ok(BuildVersion(
        captures[1].parse()?,
        captures[2].parse()?,
        captures[3].parse()?,
        captures[4].parse()?,
    ))
}

impl InstallInfo {
    pub fn gather(ds_path: &Path) -> anyhow::Result<InstallInfo> {
        // If the path does not exist or is not a directory, 
        if !ds_path.try_exists()? {
            debug!("Dedicated server directory does not exist: {:?}", ds_path);
            return Ok(InstallInfo::default());
        }

        // If the path points to a file, it has to be removed first
        if !ds_path.is_dir() {
            return Err(io::Error::new(io::ErrorKind::AlreadyExists, "Dedicated Server path exists, but is not a directory!").into());
        }

        // If server executable does not exist, count installation as not present
        let exec_path = ds_path.join(DS_EXECUTABLE_PATH);
        if !exec_path.exists() || !exec_path.is_file() {
            debug!("Dedicated server excutable file does not exist: {:?}", exec_path);
            return Ok(InstallInfo::default());
        }

        // If server wrapper executable does not exist, count installation as not present
        let wrapper_path = ds_path.join(DS_WRAPPER_PATH);
        if !wrapper_path.exists() || !wrapper_path.is_file() {
            debug!("Dedicated server wrapper excutable file does not exist: {:?}", wrapper_path);
            return Ok(InstallInfo::default());
        }

        // If server build version file does not exist, count installation as present, but don't read build version
        let build_version_path = ds_path.join(DS_BUILD_VERSION_PATH);
        if !build_version_path.exists() || !build_version_path.is_file() {
            debug!("Dedicated server build version file does not exist: {:?}", build_version_path);
            return Ok(InstallInfo {
                present: true,
                build_version: None,
            });
        }

        match parse_build_version_file(&build_version_path) {
            Ok(build_version) => {
                Ok(InstallInfo {
                    present: true,
                    build_version: Some(build_version),
                })
            },
            Err(e) => {
                error!("Error while reading build version: {:?}", e);
                Ok(InstallInfo {
                    present: true,
                    build_version: None,
                })
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::*;

    const BUILD_VERSION_PATH: &str = concatcp!("resources",MAIN_SEPARATOR,"test",MAIN_SEPARATOR,"server_environment",MAIN_SEPARATOR,"build.version");
    const SERVER_ENVIRONMENT_PATH: &str = concatcp!("resources",MAIN_SEPARATOR,"test",MAIN_SEPARATOR,"server_environment");

    #[test]
    fn read_basic_build_file() {
        let mut d = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        d.push(BUILD_VERSION_PATH);

        let res = parse_build_version_file(&d);
        assert!(res.is_ok());
        let res = res.unwrap();
        assert_eq!(res.0, 1);
        assert_eq!(res.1, 33);
        assert_eq!(res.2, 14);
        assert_eq!(res.3, 0);
    }

    #[test]
    fn build_version_comparison() {
        assert!(BuildVersion(1,2,3,4) < BuildVersion(1,2,3,5));
        assert!(BuildVersion(1,2,3,4) < BuildVersion(1,2,4,4));
        assert!(BuildVersion(2,2,3,4) > BuildVersion(1,3,4,5));
    }

    #[test]
    fn valid_server_environment() {
        let mut d = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        d.push(SERVER_ENVIRONMENT_PATH);

        let res = InstallInfo::gather(&d);
        assert!(res.is_ok());
        let res = res.unwrap();
        assert_eq!(res.present, true);
        assert_eq!(res.build_version, Some(BuildVersion(1,33,14,0)));
    }
}