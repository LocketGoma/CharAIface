# Chara-i-face

A local-first desktop AI companion app for you and your partner character.

> This project uses AI-assisted design and development.

**Chara-i-face / CharAIface** is a desktop AI companion interface that combines
local AI, optional cloud AI, file-analysis tools, and character-based
interaction.

CharAIface is designed as a character-style desktop chat app, not as a raw AI
model management console. It gives everyday users a friendly chat surface while
keeping model, routing, character-pack, and developer settings available when
needed.

## Table of Contents

- [Overview](#overview)
- [Current Status](#current-status)
- [Features](#features)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Character Packs](#character-packs)
- [File Input and Export](#file-input-and-export)
- [Development](#development)
- [Roadmap](#roadmap)
- [License](#license)
- [한국어](#한국어)

---

## Overview

CharAIface aims to provide:

- A ChatGPT-like desktop chat interface
- Lightweight local AI for casual conversation
- Optional cloud AI routing for heavier tasks
- Character packs with custom speech style, images, and themes
- File input and analysis support for text, tables, spreadsheets, and source code
- Manual file export for assistant answers
- Local model management with beginner-friendly recommendations
- Optional developer mode for advanced users

## Current Status

This project is in active alpha-stage development.

The current repository includes:

- Desktop app UI based on PySide6
- FastAPI backend service
- Local AI integration through Ollama
- Optional cloud AI integration
- Character pack loading, import, and export
- `.charpack` archive documentation
- File analysis helper tools for CSV, TSV, XLSX, text, Markdown, and source code
- Korean and English UI localization

Alpha builds may still contain unfinished packaging, rough UI edges, and
changing internal APIs.

## Features

### Desktop Chat Interface

- Chat-style desktop UI
- Central conversation log
- Bottom message input
- Character image and state display
- Session list and session controls
- Settings, model, theme, and character selection controls

### Local AI System

- Uses local AI models for casual conversation
- Supports local model selection
- Integrates with Ollama
- Recommends lightweight models by default
- Warns users before using larger local models

### Cloud AI Routing

- Routes heavier requests to cloud AI when configured
- Intended for coding, technical explanations, long documents, and complex
  reasoning
- Can rewrite cloud responses into the selected character's style

### File Analysis Tools

CharAIface includes backend file-analysis helpers so the model does not need to
guess from raw file text alone.

Supported input categories:

- Documents: `.txt`, `.md`, `.json`, `.log`, and similar text files
- Tables: `.csv`, `.tsv`
- Spreadsheets: `.xlsx`
- Source/config files: major source code and config text formats

The app can provide parsed structure, schema, samples, statistics, and tool
results to the AI model. The model still interprets the user's intent and uses
the tool output to answer.

### Manual File Export

Assistant answers can be exported manually as:

- TXT
- Markdown
- CSV
- PDF

The app returns an openable file link after export.

### Character Pack System

User character packs are stored as folders under:

```text
Windows: Documents\CharAIface\characters\
macOS: ~/Library/Application Support/CharAIface/characters/
Linux: $XDG_DATA_HOME/CharAIface/characters/ or ~/.local/share/CharAIface/characters/
```

The app creates the user data folder and the `characters` and `chat_sessions`
subfolders on first launch.

Each character pack uses one subfolder:

```text
characters/
  character_id/
    manifest.json
    style.md
    style.short.md
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
- Core and full speech style prompts
- State images
- Theme overrides

Character IDs are matched case-insensitively, so IDs that differ only by letter
case are treated as duplicates. User character packs can also be imported and
exported as `.charpack` archives. For the full archive format and policy, see
[CHARPACK.md](CHARPACK.md).

### Built-in Mascots

The built-in mascot characters are managed internally as character packs, but
their official artwork, prompts, relationship data, and private interaction
settings are not intended to be exposed as normal user character pack files.

### Character State System

Supported character states:

```text
idle
user_typing
thinking
searching
assistant_typing
assistant_done
embarrassed
panic
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

Character-specific themes use:

```text
base_theme + palette_override
```

### Localization System

UI text is managed through CSV files.

```text
resources/locales/ui.csv
Tools/locales/ui.csv
```

Initial supported languages:

- Korean
- English

Additional languages can be added by adding new columns to the CSV files and
connecting the language option in the app.

### Developer Mode

Developer mode changes user-friendly terms into technical terms.

| Normal Mode | Developer Mode |
|---|---|
| AI Model | LLM |
| Local AI | Local Model |
| Cloud AI | Cloud Model |
| Speech Style Conversion | Style Rewriter |
| Conversation Memory | Context Size |
| Auto Select | Routing Mode |

## Quick Start

### Requirements

- Python 3.11 or newer
- macOS or Windows
- Ollama for local AI, recommended for the local-first experience
- Optional cloud AI API key if using cloud routing

### macOS

Run:

```bash
./run_macos.sh
```

You can also double-click:

```text
run_macos.command
```

The launcher checks the virtual environment and runs the installer when needed.

### Windows

Run from PowerShell:

```powershell
.\run_windows.ps1
```

The launcher checks the virtual environment and runs the installer when needed.

### Manual Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Project Structure

```text
backend/                 FastAPI backend and AI services
desktop/                 PySide6 desktop app
resources/               App resources, built-in data, localization, characters
shared/                  Shared schemas and file intake helpers
Tools/                   Character pack generator/editor tool
scripts/                 Install and launch helper scripts
CHARPACK.md              Character pack archive specification
requirements.txt         Runtime dependencies
pyproject.toml           Project metadata and dependency groups
```

## Configuration

CharAIface reads runtime settings from the app settings file and environment
configuration.

Useful files:

```text
.env.example
resources/data/settings.json.example
```

Local AI defaults to Ollama at:

```text
http://127.0.0.1:11434
```

The desktop app communicates with the backend through the local backend helper.

## Character Packs

Character packs can be used in two forms:

- Folder packs under the per-user `CharAIface/characters/` data directory
- `.charpack` archives for import/export

On Windows, chat session data is saved under `Documents\CharAIface\chat_sessions\`.
For source checkout and development compatibility, `resources/characters/` is
also scanned when it exists. Packaged builds should use the user directory
instead of editing bundled runtime files.

For the complete format, import/export policy, duplicate ID behavior, and Korean
documentation, see [CHARPACK.md](CHARPACK.md).

## File Input and Export

The file input path is designed around a tool layer:

1. The app reads the file safely.
2. The backend/file helper parses structure and useful metadata.
3. The AI model interprets the user's request.
4. The model uses the helper context or tool result to answer.

The app should avoid hardcoded case-by-case answers. File-analysis tools should
provide reliable structure and calculations, while the model decides how to use
them for the user's request.

Manual export is intentionally user-triggered. If the user asks to export an
assistant answer, the app saves that answer and returns an openable link.

## Development

Common checks:

```bash
.venv/bin/python -m py_compile backend/app/services/file_export_response.py
.venv/bin/python -m py_compile desktop/ui/main_window.py
```

Development dependencies are listed in `pyproject.toml` under the `dev`
dependency group.

Tests and packaging are still being organized for alpha releases. Keep generated
artifacts and temporary workspace files out of source control unless they are
intentional release assets.

## Roadmap

Near-term work:

- Import/export UX stabilization
- Release packaging for alpha builds
- Alpha release notes
- Character pack import/export polish
- File-analysis tool result formatting
- Better real-world scenario testing for file input and export

Future ideas:

- Browser quick question add-on
- Voice input
- Tool plugins
- Update notification system
- More languages
- More character pack authoring tools

## License

CharAIface uses a split license model.

### Source Code

The source code of CharAIface is licensed under the GNU General Public License
v3.0.

You may use, study, modify, and redistribute the source code under the terms of
the GPLv3. Modified versions of the code must also be distributed under the
GPLv3.

See [LICENSE](./LICENSE) for details.

### Official Assets and Branding

You may not copy, redistribute, sell, modify, or use official assets or branding
in derivative versions without explicit written permission.

Forks and derivative versions must remove or replace the official CharAIface
mascot characters, artwork, private prompts, and branding unless they have
explicit written permission.

These assets are © 2026 Locketgoma. All rights reserved.

---

# 한국어

**Chara-i-face / CharAIface**는 로컬 AI, 선택적 클라우드 AI, 파일 분석
도구, 캐릭터 기반 상호작용을 결합한 데스크톱 AI 컴패니언 앱입니다.

이 프로젝트는 원시 AI 모델 관리 도구가 아니라, 캐릭터와 대화하는 형태의
데스크톱 채팅 앱을 목표로 합니다. 일반 사용자는 친숙한 채팅 UI를 사용하고,
필요한 경우 개발자나 고급 사용자가 모델, 라우팅, 캐릭터팩, 개발자 설정을
조정할 수 있습니다.

## 목차

- [개요](#개요)
- [현재 상태](#현재-상태)
- [주요 기능](#주요-기능)
- [빠른 시작](#빠른-시작)
- [프로젝트 구조](#프로젝트-구조)
- [설정](#설정)
- [캐릭터팩](#캐릭터팩)
- [파일 입력과 내보내기](#파일-입력과-내보내기)
- [개발](#개발)
- [로드맵](#로드맵)
- [라이선스](#라이선스)

## 개요

CharAIface가 목표로 하는 기능:

- ChatGPT와 비슷한 데스크톱 채팅 인터페이스
- 가벼운 로컬 AI 기반 일상 대화
- 무거운 작업을 위한 선택적 클라우드 AI 라우팅
- 말투, 이미지, 테마를 가진 캐릭터팩
- 텍스트, 표, 스프레드시트, 소스 코드 파일 입력과 분석
- AI 답변의 수동 파일 내보내기
- 초보자 친화적인 로컬 모델 관리
- 고급 사용자를 위한 개발자 모드

## 현재 상태

이 프로젝트는 현재 알파 단계로 개발 중입니다.

현재 저장소에 포함된 항목:

- PySide6 기반 데스크톱 앱 UI
- FastAPI 백엔드 서비스
- Ollama 기반 로컬 AI 연동
- 선택적 클라우드 AI 연동
- 캐릭터팩 로딩, 가져오기, 내보내기
- `.charpack` 아카이브 문서
- CSV, TSV, XLSX, 텍스트, Markdown, 소스 코드용 파일 분석 보조 도구
- 한국어/영어 UI 현지화

알파 빌드에는 아직 완성되지 않은 패키징, 다듬는 중인 UI, 변경 가능한 내부
API가 남아 있을 수 있습니다.

## 주요 기능

### 데스크톱 채팅 UI

- 채팅형 데스크톱 UI
- 중앙 대화 로그
- 하단 메시지 입력창
- 캐릭터 이미지와 상태 표시
- 세션 목록 및 세션 제어
- Settings, 모델, 테마, 캐릭터 선택

### 로컬 AI

- 일상 대화용 로컬 AI 모델 사용
- 로컬 모델 선택
- Ollama 연동
- 기본적으로 가벼운 모델 추천
- 큰 로컬 모델 사용 전 경고

### 클라우드 AI 라우팅

- 설정된 경우 무거운 요청을 클라우드 AI로 라우팅
- 코딩, 기술 설명, 긴 문서, 복잡한 추론에 사용
- 선택한 캐릭터 말투로 응답을 다시 변환 가능

### 파일 분석 도구

CharAIface는 모델이 원본 파일 텍스트를 눈대중으로 추측하지 않도록 백엔드
파일 분석 보조 도구를 제공합니다.

지원 입력 범주:

- 문서: `.txt`, `.md`, `.json`, `.log` 등 텍스트 파일
- 테이블: `.csv`, `.tsv`
- 스프레드시트: `.xlsx`
- 소스/설정 파일: 주요 소스 코드 및 설정 텍스트 파일

앱은 파싱된 구조, 스키마, 샘플, 통계, 도구 결과를 AI 모델에 전달할 수
있습니다. 사용자의 의도를 해석하고 결과를 설명하는 일은 여전히 모델이
담당합니다.

### 수동 파일 내보내기

AI 답변은 사용자의 명령으로 다음 형식으로 내보낼 수 있습니다.

- TXT
- Markdown
- CSV
- PDF

내보내기가 끝나면 앱은 바로 열 수 있는 파일 링크를 반환합니다.

### 캐릭터팩

사용자 캐릭터팩은 다음 위치의 폴더로 둘 수 있습니다.

```text
resources/characters/
  character_id/
    manifest.json
    style.md
    style.short.md
    idle.png
    user_typing.gif
    thinking.apng
    assistant_typing.gif
    assistant_done.png
    error.png
```

캐릭터팩은 다음 정보를 정의할 수 있습니다.

- 캐릭터 이름
- 설명
- 제작자
- 버전
- 핵심/전체 말투 스타일 프롬프트
- 상태 이미지
- 테마 override

캐릭터 ID 비교는 대소문자를 구분하지 않습니다. 예를 들어 ID의 대소문자만
다른 캐릭터팩은 중복으로 취급됩니다. 사용자 캐릭터팩은 `.charpack`
아카이브로 가져오거나 내보낼 수도 있습니다. 자세한 형식과 정책은
[CHARPACK.md](CHARPACK.md)를 참고하세요.

## 빠른 시작

### 요구 사항

- Python 3.11 이상
- macOS 또는 Windows
- 로컬 AI 경험을 위한 Ollama 권장
- 클라우드 라우팅 사용 시 선택적 클라우드 AI API 키

### macOS

실행:

```bash
./run_macos.sh
```

또는 다음 파일을 더블클릭할 수 있습니다.

```text
run_macos.command
```

런처는 가상환경을 확인하고 필요한 경우 설치 스크립트를 실행합니다.

### Windows

PowerShell에서 실행:

```powershell
.\run_windows.ps1
```

런처는 가상환경을 확인하고 필요한 경우 설치 스크립트를 실행합니다.

### 수동 설치

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 프로젝트 구조

```text
backend/                 FastAPI 백엔드와 AI 서비스
desktop/                 PySide6 데스크톱 앱
resources/               앱 리소스, 내장 데이터, 현지화, 캐릭터
shared/                  공유 스키마와 파일 입력 보조 코드
Tools/                   캐릭터팩 생성/편집 도구
scripts/                 설치 및 실행 보조 스크립트
CHARPACK.md              캐릭터팩 아카이브 사양
requirements.txt         런타임 의존성
pyproject.toml           프로젝트 메타데이터와 개발 의존성
```

## 설정

유용한 예시 파일:

```text
.env.example
resources/data/settings.json.example
```

로컬 AI의 기본 Ollama 주소:

```text
http://127.0.0.1:11434
```

데스크톱 앱은 로컬 백엔드 헬퍼를 통해 백엔드와 통신합니다.

## 파일 입력과 내보내기

파일 입력은 도구 계층을 기준으로 설계되어 있습니다.

1. 앱이 파일을 안전하게 읽습니다.
2. 백엔드 또는 파일 헬퍼가 구조와 메타데이터를 파싱합니다.
3. AI 모델이 사용자의 요청 의도를 해석합니다.
4. 모델은 보조 컨텍스트나 도구 결과를 사용해 답변합니다.

앱은 하드코딩된 case-by-case 답변을 피해야 합니다. 파일 분석 도구는 안정적인
구조와 계산 결과를 제공하고, 모델은 그 결과를 사용해 사용자의 요청에 맞는
답변을 생성합니다.

내보내기는 사용자가 명시적으로 요청했을 때 수행됩니다. AI 답변을 내보내면
앱이 파일을 저장하고 열 수 있는 링크를 반환합니다.

## 개발

개발 의존성은 `pyproject.toml`의 `dev` dependency group에 정리되어 있습니다.

알파 릴리즈를 준비하면서 테스트, 패키징, 임시 파일 정책은 계속 정리 중입니다.
생성물과 임시 workspace 파일은 의도된 릴리즈 asset이 아니라면 소스 관리에
넣지 않는 것을 권장합니다.

## 로드맵

가까운 작업:

- import/export UX 안정화
- 알파 빌드 패키징
- 알파 릴리즈 노트 작성
- 캐릭터팩 가져오기/내보내기 폴리싱
- 파일 분석 도구 결과 포맷 정리
- 실제 사용 시나리오 기반 파일 입력/내보내기 테스트

향후 아이디어:

- 브라우저 quick question 애드온
- 음성 입력
- 도구 플러그인
- 업데이트 알림 시스템
- 추가 언어
- 캐릭터팩 제작 도구 강화

## 라이선스

CharAIface는 분리된 라이선스 모델을 사용합니다.

### 소스 코드

CharAIface의 소스 코드는 GNU General Public License v3.0으로 라이선스됩니다.

소스 코드는 GPLv3 조건에 따라 사용, 학습, 수정, 재배포할 수 있습니다. 수정된
버전의 코드 역시 GPLv3로 배포되어야 합니다.

자세한 내용은 [LICENSE](./LICENSE)를 참고하세요.

### 공식 asset 및 브랜딩

명시적인 서면 허가 없이 공식 asset이나 브랜딩을 파생 버전에서 복사, 재배포,
판매, 수정, 사용할 수 없습니다.

fork 및 파생 버전은 명시적인 서면 허가가 없는 한 공식 CharAIface 마스코트
캐릭터, 아트워크, private prompt, 브랜딩을 제거하거나 교체해야 합니다.

해당 asset은 © 2026 Locketgoma. All rights reserved.
