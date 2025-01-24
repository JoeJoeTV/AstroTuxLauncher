/// Module: notifications
/// File: discord.rs
/// Author: JoeJoeTV
/// Description: Contains models for use with Discord's Webhooks

use thiserror::Error;

use hex_color::HexColor;
use jiff::Timestamp;
use serde::{Deserialize, Serialize};
use serde_nested_with::serde_nested;
use url::Url;

#[derive(Debug, Error)]
pub enum DiscordWebhookError {
    #[error("A webhook message can't have more than {max} embeds", max = 10)]
    TooManyEmbeds,
    #[error("An embed can't have more than {max} fields", max = 25)]
    TooManyFields,
}

#[derive(Debug, Serialize, Default)]
pub struct WebhookMessage {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub username: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub avatar_url: Option<Url>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tts: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub embeds: Option<Vec<Embed>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub flags: Option<WebhookMessageFlags>,
}

impl WebhookMessage {
    /// Creates new empty message object
    pub fn new() -> Self {
        Self::default()
    }

    /// Sets the content of the message
    pub fn content(mut self, value: &str) -> Self {
        self.content = Some(value.to_owned());
        self
    }

    /// Sets the username of the message
    pub fn username(mut self, value: &str) -> Self {
        self.username = Some(value.to_owned());
        self
    }

    /// Sets the avatar URL of the message
    pub fn avatar_url(mut self, value: Url) -> Self {
        self.avatar_url = Some(value);
        self
    }

    /// Sets whether the message should be a tts message
    pub fn tts(mut self, value: bool) -> Self {
        self.tts = Some(value);
        self
    }

    /// Adds an embed to the message
    pub fn add_embed<Func>(mut self, func: Func) -> Result<Self, DiscordWebhookError>
    where
        Func: Fn(Embed) -> Embed,
    {
        let embed = func(Embed::new());
        
        if let Some(ref mut embeds) = self.embeds {
            if embeds.len() >= 10 {
                return Err(DiscordWebhookError::TooManyEmbeds);
            }
            embeds.push(embed);
        } else {
            self.embeds = Some(vec![embed]);
        }

        Ok(self)
    }

    /// Sets the "Supress Embeds" flag
    pub fn supress_embeds(mut self, value: bool) -> Self {
        if let Some(flags) = &mut self.flags {
            flags.supress_embeds = value;
        } else {
            let mut flags = WebhookMessageFlags::default();
            flags.supress_embeds = value;
            self.flags = Some(flags);
        }
        self
    }

    /// Sets the "Supress Notifications" flag
    pub fn supress_notifications(mut self, value: bool) -> Self {
        if let Some(flags) = &mut self.flags {
            flags.supress_notifications = value;
        } else {
            let mut flags = WebhookMessageFlags::default();
            flags.supress_notifications = value;
            self.flags = Some(flags);
        }
        self
    }
}

#[serde_nested]
#[derive(Debug, Serialize)]
pub struct Embed {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub r#type: Option<EmbedType>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub url: Option<Url>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timestamp: Option<Timestamp>,
    #[serde(skip_serializing_if = "Option::is_none")]
    #[serde_nested(sub = "HexColor", serde(with = "hex_color::u24"))]
    pub color: Option<HexColor>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub footer: Option<EmbedFooter>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub image: Option<EmbedImage>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub thumbnail: Option<EmbedThumbnail>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub video: Option<EmbedVideo>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub provider: Option<EmbedProvider>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub author: Option<EmbedAuthor>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fields: Option<Vec<EmbedField>>
}

impl Default for Embed {
    fn default() -> Self {
        Self{
            title: None,
            r#type: Some(EmbedType::Rich),
            description: None,
            url: None,
            timestamp: None,
            color: None,
            footer: None,
            image: None,
            thumbnail: None,
            video: None,
            provider: None,
            author: None,
            fields: None,
        }
    }
}

impl Embed {
    /// Creates new empty embed object
    pub fn new() -> Self {
        Self::default()
    }

    /// Sets the title of this embed
    pub fn title(mut self, value: &str) -> Self {
        self.title = Some(value.to_owned());
        self
    }

    /// Sets the title of this embed
    pub fn r#type(mut self, value: EmbedType) -> Self {
        self.r#type = Some(value);
        self
    }

    /// Sets the description of this embed
    pub fn description(mut self, value: &str) -> Self {
        self.description = Some(value.to_owned());
        self
    }

    /// Sets the url of this embed
    pub fn url(mut self, value: Url) -> Self {
        self.url = Some(value);
        self
    }

    /// Sets the timestamp of this embed
    pub fn timestamp(mut self, value: Timestamp) -> Self {
        self.timestamp = Some(value);
        self
    }

    /// Sets the color of this embed
    pub fn color(mut self, value: HexColor) -> Self {
        self.color = Some(value);
        self
    }

    /// Sets the footer of this embed
    pub fn footer(mut self, text: &str, icon_url: Option<Url>, proxy_icon_url: Option<Url>) -> Self {
        self.footer = Some(EmbedFooter{
            text: text.to_owned(),
            icon_url: icon_url,
            proxy_icon_url: proxy_icon_url,
        });
        self
    }

    /// Sets the image of this embed
    pub fn image(mut self, url: Url, proxy_url: Option<Url>, height: Option<i32>, width: Option<i32>) -> Self {
        self.image = Some(EmbedImage{
            url: url,
            proxy_url: proxy_url,
            height: height.to_owned(),
            width: width.to_owned(),
        });
        self
    }

    /// Sets the thumbnail of this embed
    pub fn thumbnail(mut self, url: Url, proxy_url: Option<Url>, height: Option<i32>, width: Option<i32>) -> Self {
        self.thumbnail = Some(EmbedThumbnail{
            url: url,
            proxy_url: proxy_url,
            height: height.to_owned(),
            width: width.to_owned(),
        });
        self
    }

    /// Sets the video of this embed
    pub fn video(mut self, url: Url, proxy_url: Option<Url>, height: Option<i32>, width: Option<i32>) -> Self {
        self.video = Some(EmbedVideo{
            url: url,
            proxy_url: proxy_url,
            height: height.to_owned(),
            width: width.to_owned(),
        });
        self
    }

    /// Sets the provider of this embed
    pub fn provider(mut self, name: Option<String>, url: Option<Url>) -> Self {
        self.provider = Some(EmbedProvider{
            name: name,
            url: url,
        });
        self
    }

    /// Sets the author of this embed
    pub fn author(mut self, name: &str, url: Option<Url>, icon_url: Option<Url>, proxy_icon_url: Option<Url>) -> Self {
        self.author = Some(EmbedAuthor{
            name: name.to_owned(),
            url: url,
            icon_url: icon_url,
            proxy_icon_url: proxy_icon_url,
        });
        self
    }

    /// Adds a field to the embed
    pub fn add_field(mut self, name: &str, value: &str, inline: Option<bool>) -> Result<Self, DiscordWebhookError> {
        let field = EmbedField{
            name: name.to_owned(),
            value: value.to_owned(),
            inline: inline,
        };

        if let Some(fields) = &mut self.fields {
            if fields.len() >= 25 {
                return Err(DiscordWebhookError::TooManyFields);
            }
            fields.push(field);
        } else {
            self.fields = Some(vec![field]);
        }

        Ok(self)
    }

}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all(serialize = "snake_case", deserialize = "snake_case"))]
pub enum EmbedType {
    Rich,
    Image,
    Video,
    Gifv,
    Article,
    Link,
    PollResult,
}

#[derive(Debug, Serialize)]
pub struct EmbedFooter {
    pub text: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub icon_url: Option<Url>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub proxy_icon_url: Option<Url>,
}

#[derive(Debug, Serialize)]
pub struct EmbedImage {
    pub url: Url,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub proxy_url: Option<Url>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub height: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub width: Option<i32>,
}

#[derive(Debug, Serialize)]
pub struct EmbedThumbnail {
    pub url: Url,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub proxy_url: Option<Url>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub height: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub width: Option<i32>,
}

#[derive(Debug, Serialize)]
pub struct EmbedVideo {
    pub url: Url,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub proxy_url: Option<Url>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub height: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub width: Option<i32>,
}

#[derive(Debug, Serialize)]
pub struct EmbedProvider {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub url: Option<Url>,
}

#[derive(Debug, Serialize)]
pub struct EmbedAuthor {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub url: Option<Url>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub icon_url: Option<Url>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub proxy_icon_url: Option<Url>,
}

#[derive(Debug, Serialize)]
pub struct EmbedField {
    pub name: String,
    pub value: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub inline: Option<bool>,
}

#[derive(Debug)]
pub struct WebhookMessageFlags {
    pub supress_embeds: bool,
    pub supress_notifications: bool,
}

impl Default for WebhookMessageFlags {
    fn default() -> Self {
        Self{
            supress_embeds: false,
            supress_notifications: false,
        }
    }
}

impl Serialize for WebhookMessageFlags {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer {
            let mut bitfield: u16 = 0;

            if self.supress_embeds {
                bitfield |= 1 << 2;
            }

            if self.supress_notifications {
                bitfield |= 1 << 12;
            }

            serializer.serialize_u16(bitfield)
    }
}