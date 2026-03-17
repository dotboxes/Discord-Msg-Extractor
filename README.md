

# 📦 Discord Message Extractor Bot

A Python Discord bot that extracts content from messages and converts them into a web-friendly format, supporting images, videos, embeds, and external links from multiple platforms.

---

## 🌟 Features

### ✅ Discord Message Extraction

* Extract text content from messages
---

### 🌐 Platform Support

| Platform          | Images                                                                  | Videos                                                                    | Notes                                                                          |
| ----------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **Instagram**     | ![green](https://img.shields.io/badge/Images-✅-green?style=flat-square) | ![yellow](https://img.shields.io/badge/Reels-🆗-yellow?style=flat-square) | Shows thumbnail for Reels; play button overlay; do **not** use `kkinstagram` |
| **X (Twitter)**   | ![green](https://img.shields.io/badge/Images-✅-green?style=flat-square) | ![green](https://img.shields.io/badge/Videos-✅-green?style=flat-square)   | Works for posts with images and videos                                         |
| **fxtwitter**     | ![green](https://img.shields.io/badge/Images-✅-green?style=flat-square) | ![green](https://img.shields.io/badge/Videos-✅-green?style=flat-square)   | Twitter video support via `fxtwitter`                                          |
| **vxtwitter**     | ![green](https://img.shields.io/badge/Images-✅-green?style=flat-square) | ![green](https://img.shields.io/badge/Videos-✅-green?style=flat-square)   | Alternate Twitter video extractor                                              |
| **TikTok**        | ![red](https://img.shields.io/badge/Images-❌-red?style=flat-square)     | ![red](https://img.shields.io/badge/Videos-❌-red?style=flat-square)       | Currently not supported                                                        |
| **Reddit**        | ![red](https://img.shields.io/badge/Images-❌-red?style=flat-square)     | ![red](https://img.shields.io/badge/Videos-❌-red?style=flat-square)       | Currently not supported                                                        |
| **YouTube**       | ![green](https://img.shields.io/badge/Images-✅-green?style=flat-square) | ![green](https://img.shields.io/badge/Videos-✅-green?style=flat-square)   | Extracts video links and thumbnails                                            |
| **Generic Links** | ![green](https://img.shields.io/badge/Links-✅-green?style=flat-square)  | ![green](https://img.shields.io/badge/Videos-✅-green?style=flat-square)     | Works for most sites, some broken links                                        |
> [!WARNING]
> Due to Discord's own limitations, source URL to files/attachments/images/videos in the message cannot be extracted.
---

## ⚙️ Installation

```bash
git clone https://github.com/yourusername/discord-message-extractor.git
cd discord-message-extractor

python3 -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file:

```env
DISCORD_TOKEN=your-discord-bot-token
GUILD_ID=your-guild-id
PURGE_ROLE_ID=role-id-for-higher-permissions

API_URL=https://your-domain.com
```

---

## 🚀 Usage

```bash
python main.py
```

* `!extract <message_id>` – Extracts all content from a Discord message.
* `!help` – Lists commands.

---

## 💻 Website Integration

The bot outputs extracted media and links in a structured format:

* Markdown-friendly formatting
* Embeds for supported platforms
* Images stored locally or in cloud storage
* Link previews and thumbnails

---

## ⚠️ Limitations

* TikTok and Reddit extraction not supported
* Some generic links may fail
* Discord videos not downloadable yet

---

## 🛠 Contributing

* Fork → Branch → PR
* Contributions welcome!

--- 

## 📧 Support

Open a GitHub issue for bugs or questions.

---

✅ Built with **Python** and `discord.py`
