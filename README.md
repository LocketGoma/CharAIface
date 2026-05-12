# Chara-i-face
Local AI Companion App For you &amp; your Partner Character.

- This Project Supported by GPT-5.5.

**Chara-i-face** is a desktop AI companion interface that combines lightweight local AI, cloud AI, and character-based interaction.

CharAIface is designed as a character-style desktop chat app, not as a raw AI model management tool. It provides a friendly chat interface for everyday users while keeping advanced AI/model settings available for developers.


---

## Overview

CharAIface aims to provide:

- A ChatGPT-like desktop chat interface
- Lightweight local AI for casual conversation
- Cloud AI routing for heavier tasks such as coding, technical explanations, and long-form reasoning
- Character packs with custom speech style, images, and themes
- Local model management with beginner-friendly recommendations
- Optional developer mode for advanced users

---

## Target Users

CharAIface is designed for users who:

- Use PCs frequently
- Are comfortable with apps such as games, Discord, Steam, launchers, and settings menus
- Are not necessarily familiar with AI model terms such as LLM, context size, quantization, RAM usage, or routing
- Prefer recommended settings over complicated configuration
- Want a character-based AI companion rather than a technical AI console

---

## Main Systems

### Desktop Chat Interface

- ChatGPT-style desktop UI
- Central chat log
- Bottom message input
- Character image and state display
- Settings, model, and character selection controls

### Local AI System

- Uses lightweight local AI models for casual conversation
- Supports local model selection
- Supports style rewriting through a local model
- Recommends lightweight models by default
- Warns users before using large local models

### Cloud AI Routing

- Routes heavier requests to cloud AI
- Intended for coding, technical explanations, long documents, and complex reasoning
- Can rewrite cloud responses into the selected character's style

### Character Pack System

Character packs are stored as folders under:

```text
characters/
  character_id/
    manifest.json
    style.md
    idle.png
    user_typing.gif
    thinking.apng
    assistant_typing.gif
    assistant_done.png
    error.png
```

A valid character pack can define:

- Character name
- Description
- Author
- Version
- Speech style prompt
- State images
- Theme overrides

### Built-in Mascots

CharAIface plans to include two official mascot characters.

The built-in mascots are managed internally as character packs, but their official artwork, prompts, relationship data, and private interaction settings are not intended to be exposed as normal user character pack files.

### Character State System

Supported character states:

```text
idle
user_typing
thinking
searching
assistant_typing
assistant_done
error
```

Supported image formats:

```text
jpg
jpeg
png
gif
apng
```

### Theme System

Theme modes:

- Character Theme
- Light
- Dark

Common themes are stored under:

```text
themes/
  light.json
  dark.json
```

Character-specific themes use:

```text
base_theme + palette_override
```

### Localization System

UI text is managed through CSV files.

```text
locales/ui.csv
```

Initial supported languages:

- Korean
- English

Additional languages can be added by adding new columns to the CSV file.

### Model Management

CharAIface provides:

- Recommended local models
- Direct model name input for advanced users
- Installed model list
- Local model download prompts
- Local model deletion
- Large model memory warnings

General users see model options as:

- Lightweight
- Balanced
- High Quality

Developer mode can show actual model names and technical terms.

### Developer Mode

Developer mode changes user-friendly terms into technical terms.

Example:

| Normal Mode | Developer Mode |
|---|---|
| AI Model | LLM |
| Local AI | Local Model |
| Cloud AI | Cloud Model |
| Speech Style Conversion | Style Rewriter |
| Conversation Memory | Context Size |
| Auto Select | Routing Mode |

### Plugin Input System

The app is designed to support additional input sources later.

Planned input plugins:

- Desktop Chat
- Browser Quick Question
- File Context
- Voice Input
- Tool Plugins

### Browser Quick Question Add-on

Planned future feature:

- Browser overlay character
- Quick questions from selected text
- Current page summary
- Communication with the local desktop backend

### Update System

Planned future feature:

- Check for new releases
- Show release notes
- Open download page
- Update recommended model list through app releases

---

## License

CharAIface uses a split license model.

### Source Code

The source code of CharAIface is licensed under the GNU General Public License v3.0.

You may use, study, modify, and redistribute the source code under the terms of the GPLv3. Modified versions of the code must also be distributed under the GPLv3.

See [LICENSE](./LICENSE) for details.

### Official Assets and Branding

You may not copy, redistribute, sell, modify, or use these official assets or branding in derivative versions without explicit written permission.

Forks and derivative versions must remove or replace the official CharAIface mascot characters, artwork, private prompts, and branding unless they have explicit written permission.

These assets are © [2026] [Locketgoma]. All rights reserved.
