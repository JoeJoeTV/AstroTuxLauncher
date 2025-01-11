use std::{collections::HashMap, thread::JoinHandle};

use clap::{crate_name, crate_version};
use flume::{Receiver, Sender};
use hex_color::HexColor;
use jiff::Timestamp;
use log::{
    debug, info, Level, LevelFilter
};
use async_utility::blocking::Async2Blocking;
use ntfy::prelude::*;
use serde::{Deserialize, Serialize};
use ureq::Agent;
use url::Url;

#[allow(dead_code)]
mod discord;

use discord::WebhookMessage;

macro_rules! notifyerror {
    (target: $target:expr, $($arg:tt)+) => (log::log!(target: $target, log::Level::Error, from_notify=true; $($arg)+));
    ($($arg:tt)+) => (log::log!(log::Level::Error, skip_notify=true; $($arg)+))
}

const NOTIFY_APP_NAME: &str = "AstroServerManager";
const NOTIFY_ICON_URL: &str = "https://astroneer.wiki.gg/images/7/74/Icon_Astroneer.png";

#[derive(Debug, Serialize, Deserialize, Clone, Copy)]
#[serde(rename_all(serialize = "lowercase", deserialize = "lowercase"))]
pub enum NotificationLevel {
    /// Corresponds to only "Server Events" like server start/shutdown, players joining/leaving, etc. are sent
    Server,
    /// Corresponds to the 'Error' log-level
    Error,
    /// Corresponds to the 'Warn' log-level
    Warn,
    /// Corresponds to the 'Info log-level
    Info,
}

impl Default for NotificationLevel {
    fn default() -> Self {
        NotificationLevel::Server
    }
}

impl Into<LevelFilter> for NotificationLevel {
    fn into(self) -> LevelFilter {
        match self {
            Self::Server => LevelFilter::Off,
            Self::Error => LevelFilter::Error,
            Self::Warn => LevelFilter::Warn,
            Self::Info => LevelFilter::Info,
        }
    }
}

pub enum NotificationThreadMessage {
    Message {
        message: String,
        event_id: Option<String>,
        timestamp: Timestamp,
        level: Level,
    },
    Stop,
}

impl NotificationThreadMessage {
    pub fn msg(
        message: String,
        timestamp: Timestamp,
        level: Level,
        event_id: Option<String>,
    ) -> Self {
        Self::Message {
            message,
            timestamp,
            level,
            event_id,
        }
    }
}
pub trait NotificationThread {
    /// Gets the Sender used to send messages to the notification thread
    fn get_sender(&self) -> Sender<NotificationThreadMessage>;
    /// Starts the notification thread
    fn start(self: Box<Self>) -> JoinHandle<()>;
}

#[derive(Debug, Serialize, Deserialize, Clone, Copy)]
#[serde(rename_all(serialize = "lowercase", deserialize = "lowercase"))]
pub enum NtfyPriority {
    Max,
    High,
    Default,
    Low,
    Min,
}

impl From<Priority> for NtfyPriority {
    fn from(value: Priority) -> Self {
        match value {
            Priority::Max => Self::Max,
            Priority::High => Self::High,
            Priority::Default => Self::Default,
            Priority::Low => Self::Low,
            Priority::Min => Self::Min,
        }
    }
}

impl Into<Priority> for NtfyPriority {
    fn into(self) -> Priority {
        match self {
            Self::Max => Priority::Max,
            Self::High => Priority::High,
            Self::Default => Priority::Default,
            Self::Low => Priority::Low,
            Self::Min => Priority::Min,
        }
    }
}

pub struct NtfyNotificationThread {
    topic: String,
    emojis: HashMap<String, String>,
    priorities: HashMap<String, NtfyPriority>,
    dispatcher: Dispatcher,
    channel: (
        Sender<NotificationThreadMessage>,
        Receiver<NotificationThreadMessage>,
    ),
}

impl NtfyNotificationThread {
    pub fn new(
        server_url: Url,
        topic: String,
        emojis: HashMap<String, String>,
        priorities: HashMap<String, NtfyPriority>,
    ) -> Result<Box<dyn NotificationThread>, NtfyError> {
        let channel = flume::unbounded();

        let thread = NtfyNotificationThread {
            topic,
            emojis,
            dispatcher: Dispatcher::builder(server_url).build()?,
            channel,
            priorities,
        };

        Ok(Box::new(thread))
    }

    fn run(self) {
        debug!(from_notify=true; "Starting ntfy notification thread...");

        loop {
            match self.channel.1.recv() {
                Err(_) => break,
                Ok(tmsg) => match tmsg {
                    NotificationThreadMessage::Stop => break,
                    NotificationThreadMessage::Message {
                        message,
                        event_id,
                        timestamp: _,
                        level,
                    } => {
                        if let Some(event_id) = event_id {
                            // If emoji tag is present, get it and add it together with other tags
                            let tags = self.emojis.get(&event_id)
                                .map(|e|vec![e, NOTIFY_APP_NAME, &event_id])
                                .unwrap_or(vec![NOTIFY_APP_NAME, &event_id]);
                            let priority: Priority = self.priorities.get(&event_id)
                                .map(|p|(*p).into())
                                .unwrap_or(Priority::Default);

                            let payload = Payload::new(&self.topic)
                                .title(message)
                                .message(NOTIFY_APP_NAME)
                                .tags(tags)
                                .priority(priority);

                                self.dispatcher.send(&payload).blocking().unwrap();
                        } else {
                            let title: &str;
                            let priority: Priority;
                            let tag: &str;

                            match level {
                                Level::Error => {
                                    title = "Error";
                                    priority = Priority::Max;
                                    tag = "error";
                                },
                                Level::Warn => {
                                    title = "Warning";
                                    priority = Priority::High;
                                    tag = "warn";
                                },
                                Level::Info => {
                                    title = "Information";
                                    priority = Priority::Default;
                                    tag = "info";
                                },
                                Level::Debug => {
                                    title = "Debug";
                                    priority = Priority::Low;
                                    tag = "debug";
                                },
                                Level::Trace => {
                                    title = "Trace";
                                    priority = Priority::Min;
                                    tag = "trace";
                                },
                            }

                            let payload = Payload::new(&self.topic)
                                .message(message)
                                .title(title)
                                .tags([NOTIFY_APP_NAME, tag])
                                .priority(priority);
                            
                            self.dispatcher.send(&payload).blocking().unwrap();

                        }
                    }
                },
            }
        }
    }
}

impl NotificationThread for NtfyNotificationThread {
    fn get_sender(&self) -> Sender<NotificationThreadMessage> {
        self.channel.0.clone()
    }

    fn start(self: Box<Self>) -> JoinHandle<()> {
        std::thread::Builder::new().name("notification_thread".to_owned()).spawn(move || self.run()).unwrap()
    }
}

pub struct DiscordNotificationThread {
    webhook_url: Url,
    emojis: HashMap<String, String>,
    colors: HashMap<String, HexColor>,
    agent: Agent,
    channel: (
        Sender<NotificationThreadMessage>,
        Receiver<NotificationThreadMessage>,
    ),
}

impl DiscordNotificationThread {
    pub fn new(
        webhook_url: Url,
        emojis: HashMap<String, String>,
        colors: HashMap<String, HexColor>,
    ) -> Box<dyn NotificationThread> {
        let channel = flume::unbounded();

        let agent = ureq::builder()
            .user_agent(&format!("{}/{}", crate_name!(), crate_version!()))
            .build();

        let thread = DiscordNotificationThread {
            webhook_url,
            emojis,
            colors,
            agent,
            channel,
        };

        Box::new(thread)
    }

    fn run(self) {
        debug!(from_notify=true; "Starting discord notification thread...");

        loop {
            match self.channel.1.recv() {
                Err(_) => break,
                Ok(tmsg) => match tmsg {
                    NotificationThreadMessage::Stop => break,
                    NotificationThreadMessage::Message {
                        message,
                        event_id,
                        timestamp,
                        level,
                    } => {
                        if let Some(event_id) = event_id {
                            // If emoji tag is present, get it and add it together with other tags
                            let title = self.emojis.get(&event_id).map(|e|format!(":{}: {}", e, message)).unwrap_or(message);
                            let default_color = HexColor::parse_rgb("#2B2D31").unwrap();
                            let color = self.colors.get(&event_id).unwrap_or(&default_color);

                            let msg = WebhookMessage::new()
                                .username(NOTIFY_APP_NAME)
                                .avatar_url(Url::parse(NOTIFY_ICON_URL).unwrap())
                                .add_embed(|embed| embed
                                    .title(&title)
                                    .author("Server Event", None, None, None)
                                    .color(*color)
                                    .add_field("Event", &event_id, Some(true)).unwrap()
                                    .footer(&format!("{} v{}", NOTIFY_APP_NAME, crate_version!()), Some(Url::parse(NOTIFY_ICON_URL).unwrap()), None)
                                    .timestamp(timestamp)
                                ).unwrap();

                            self.agent.post(self.webhook_url.as_str())
                                .send_json(msg).unwrap();
                        } else {
                            let title: &str;
                            let color: HexColor;

                            match level {
                                Level::Error => {
                                    title = "Error";
                                    color = HexColor::parse_rgb("#ff0000").unwrap();
                                },
                                Level::Warn => {
                                    title = "Warning";
                                    color = HexColor::parse_rgb("#ff8500").unwrap();
                                },
                                Level::Info => {
                                    title = "Information";
                                    color = HexColor::parse_rgb("#777777").unwrap();
                                },
                                Level::Debug => {
                                    title = "Debug";
                                    color = HexColor::parse_rgb("#3c475e").unwrap();
                                },
                                Level::Trace => {
                                    title = "Trace";
                                    color = HexColor::parse_rgb("#2b2d31").unwrap();
                                },
                            }

                            let msg = WebhookMessage::new()
                                .username(NOTIFY_APP_NAME)
                                .avatar_url(Url::parse(NOTIFY_ICON_URL).unwrap())
                                .add_embed(|embed| embed
                                    .title(&title)
                                    .author("Server Message", None, None, None)
                                    .description(&message)
                                    .color(color)
                                    .footer(&format!("{} v{}", NOTIFY_APP_NAME, crate_version!()), Some(Url::parse(NOTIFY_ICON_URL).unwrap()), None)
                                    .timestamp(timestamp)
                                ).unwrap();

                            self.agent.post(self.webhook_url.as_str())
                                .send_json(msg).unwrap();
                        }
                    }
                },
            }
        }
    }
}

impl NotificationThread for DiscordNotificationThread {
    fn get_sender(&self) -> Sender<NotificationThreadMessage> {
        self.channel.0.clone()
    }

    fn start(self: Box<Self>) -> JoinHandle<()> {
        std::thread::Builder::new().name("notification_thread".to_owned()).spawn(move || self.run()).unwrap()
    }
}
