# CharAIface Character Pack Specification

This document describes the current `.charpack` archive format, folder-pack
layout, and the app policy for importing and exporting character packs.

한국어 문서는 아래의 [한국어 사양](#한국어-사양) 섹션을 참고하세요.

## Overview

A `.charpack` file is a ZIP archive with a `.charpack` extension. It contains a
single CharAIface character pack: metadata, style prompts, optional theme data,
and avatar images.

The format is intended for user character import/export. Built-in character
packs are reserved by the app and are not exported from the main Settings UI.

## Archive Layout

Recommended archive layout:

```text
manifest.json
style.md
style.short.md
images/
  idle.png
  user_typing.png
  thinking.png
  searching.png
  assistant_typing.png
  assistant_done.png
  embarrassed.png
  panic.png
  error.png
```

Required files:

- `manifest.json`
- `style.md`, or the path referenced by `manifest.style_file`
- The `idle` avatar image referenced by `manifest.avatar.images.idle`

Optional files:

- `style.short.md`
- Additional avatar state images

## Manifest

`manifest.json` defines character metadata, style file paths, avatar images,
and optional theme settings.

Required for `.charpack` archives:

- `format`: must be `charaiface.character_pack`
- `format_version`: must be `1`
- `id`: character id; ASCII letters, numbers, `_`, and `-` only
- `name`: display name
- `version`: character pack version string
- `style_file`: full style prompt file path, usually `style.md`
- `avatar.type`: currently only `image` is supported
- `avatar.images.idle`: required idle avatar image path

Optional or defaulted fields:

- `description`: short character description
- `author`: character pack author
- `style_strength`: numeric style strength, currently preserved by the app
- `theme.base_theme`: usually `light` or `dark`
- `theme.palette_override`: color override map
- Additional `avatar.images` entries for supported reaction states

Example:

```json
{
  "format": "charaiface.character_pack",
  "format_version": 1,
  "id": "sample_character",
  "name": "Sample Character",
  "version": "1.0.0",
  "description": "Example character pack.",
  "author": "CharAIface",
  "style_file": "style.md",
  "style_strength": 0.5,
  "avatar": {
    "type": "image",
    "images": {
      "idle": "images/idle.png",
      "user_typing": "images/user_typing.png",
      "thinking": "images/thinking.png",
      "searching": "images/searching.png",
      "assistant_typing": "images/assistant_typing.png",
      "assistant_done": "images/assistant_done.png"
    }
  },
  "theme": {
    "base_theme": "light",
    "palette_override": {}
  }
}
```

## Style Files

CharAIface currently uses two style files:

- `style.short.md`: core style. In the character tool UI, this is the Core area.
- `style.md`: full style. In the character tool UI, this is generated from the
  Core area plus the Support area.

Existing character folders without `style.short.md` are still valid. When such a
pack is opened in the tool, the full style is treated as the Core area and the
Support area starts empty.

At runtime, the backend may prefer the short style when character style emphasis
is disabled. The full style remains the main/default style prompt.

## Avatar Images

Supported image extensions:

- `.png`
- `.jpg`
- `.jpeg`
- `.gif`
- `.apng`

Known reaction states:

- `idle`
- `user_typing`
- `thinking`
- `searching`
- `assistant_typing`
- `assistant_done`
- `embarrassed`
- `panic`
- `error`

`idle` is required. Missing optional states fall back to other states in the app,
usually ending at `idle`.

## Folder Packs

During development, a user character pack can also exist as a folder under:

```text
resources/characters/<character_id>/
  manifest.json
  style.md
  style.short.md
  idle.png
```

The folder manifest does not need `format` or `format_version`; those fields are
required only for `.charpack` archives. When a folder pack is exported, the app
adds the archive format fields and normalizes archive image paths under
`images/`.

For convenience during manual testing, the scanner also accepts
`resources/characters/` itself as a temporary single character pack when that
folder directly contains `manifest.json`. One subfolder per character is still
recommended.

## Import Policy

The main app imports `.charpack` files into the user character directory.

Current safeguards:

- Archive paths must be relative and cannot contain `..` or backslashes.
- Empty archive paths are rejected.
- Duplicate archive paths are rejected.
- Symbolic links inside the archive are rejected.
- `manifest.json` is required.
- The archive can contain at most 64 files.
- Extracted file size is limited to 128 MiB total.
- The character id must be safe: ASCII letters, numbers, `_`, and `-`.
- Character id matching is case-insensitive.
- Built-in character ids are reserved and cannot be overwritten by import.
- If the same user character id already exists, the UI asks whether to replace
  it.
- Replacing an existing user pack creates a backup under `.backups`.
- After a successful import, the UI asks whether to select the imported
  character immediately.

## Export Policy

The main Settings UI exports user character packs to `.charpack`.

Current behavior:

- Built-in character packs are not exported from Settings.
- Missing optional image states are omitted from the archive.
- `style.md` is always exported as the full style file.
- `style.short.md` is exported when present.
- Image files are written under `images/` inside the archive.
- The target file receives the `.charpack` suffix if it is omitted.

The character tool can also save `.charpack` drafts. It uses the same archive
format and requires at least one `idle` reaction image.

## Duplicate and Version Policy

The character id is the primary identity for import conflicts. Identity matching
is case-insensitive, so `sample_character` and `Sample_Character` are treated as
the same character id.

The UI shows the existing and incoming versions when the same user id already
exists. The current implementation does not enforce semantic version ordering;
the user decides whether to replace the existing pack.

## Compatibility Notes

- `.charpack` archives require `format` and `format_version`.
- Folder packs can omit `format` and `format_version`.
- Packs without `style.short.md` remain supported.
- Only image avatar packs are supported for now.
- Binary assets other than supported image formats are not part of the current
  character pack format.

---

# 한국어 사양

이 문서는 현재 CharAIface의 `.charpack` 아카이브 형식, 폴더형 캐릭터팩
구조, 가져오기/내보내기 정책을 설명합니다.

## 개요

`.charpack` 파일은 `.charpack` 확장자를 가진 ZIP 아카이브입니다. 하나의
CharAIface 캐릭터팩을 담으며, 메타데이터, 스타일 프롬프트, 선택적 테마
정보, 아바타 이미지를 포함합니다.

이 형식은 사용자 캐릭터팩 가져오기/내보내기를 위한 형식입니다. 기본 제공
캐릭터팩은 앱에서 예약된 캐릭터팩이며, 메인 Settings UI에서는 내보낼 수
없습니다.

## 아카이브 구조

권장 아카이브 구조:

```text
manifest.json
style.md
style.short.md
images/
  idle.png
  user_typing.png
  thinking.png
  searching.png
  assistant_typing.png
  assistant_done.png
  embarrassed.png
  panic.png
  error.png
```

필수 파일:

- `manifest.json`
- `style.md`, 또는 `manifest.style_file`에서 지정한 파일
- `manifest.avatar.images.idle`에서 지정한 `idle` 아바타 이미지

선택 파일:

- `style.short.md`
- 추가 아바타 상태 이미지

## Manifest

`manifest.json`은 캐릭터 메타데이터, 스타일 파일 경로, 아바타 이미지,
선택적 테마 설정을 정의합니다.

`.charpack` 아카이브에서 필수인 필드:

- `format`: 반드시 `charaiface.character_pack`
- `format_version`: 반드시 `1`
- `id`: 캐릭터 ID. ASCII 영문자, 숫자, `_`, `-`만 허용
- `name`: 표시 이름
- `version`: 캐릭터팩 버전 문자열
- `style_file`: 전체 스타일 프롬프트 파일 경로. 보통 `style.md`
- `avatar.type`: 현재는 `image`만 지원
- `avatar.images.idle`: 필수 `idle` 아바타 이미지 경로

선택 또는 기본값이 있는 필드:

- `description`: 짧은 캐릭터 설명
- `author`: 캐릭터팩 제작자
- `style_strength`: 스타일 강도 값. 현재 앱에서는 보존됨
- `theme.base_theme`: 보통 `light` 또는 `dark`
- `theme.palette_override`: 색상 override 맵
- 지원되는 반응 상태에 대한 추가 `avatar.images` 항목

## 스타일 파일

CharAIface는 현재 두 종류의 스타일 파일을 사용합니다.

- `style.short.md`: 핵심 스타일. 캐릭터 툴 UI에서는 Core 영역에 해당합니다.
- `style.md`: 전체 스타일. 캐릭터 툴 UI에서는 Core 영역과 Support 영역을
  합쳐 생성됩니다.

`style.short.md`가 없는 기존 캐릭터 폴더도 계속 유효합니다. 이런 캐릭터팩을
툴에서 열면 전체 스타일을 Core 영역으로 취급하고 Support 영역은 비어 있는
상태로 시작합니다.

런타임에서는 캐릭터 스타일 강조가 비활성화된 경우 짧은 스타일을 우선 사용할
수 있습니다. 전체 스타일 파일은 기본 스타일 프롬프트로 유지됩니다.

## 아바타 이미지

지원 이미지 확장자:

- `.png`
- `.jpg`
- `.jpeg`
- `.gif`
- `.apng`

알려진 반응 상태:

- `idle`
- `user_typing`
- `thinking`
- `searching`
- `assistant_typing`
- `assistant_done`
- `embarrassed`
- `panic`
- `error`

`idle`은 필수입니다. 선택 상태 이미지가 없으면 앱에서 다른 상태 이미지로
fallback하며, 보통 최종적으로 `idle`을 사용합니다.

## 폴더형 캐릭터팩

개발 중에는 사용자 캐릭터팩을 다음 위치의 폴더로 둘 수도 있습니다.

```text
resources/characters/<character_id>/
  manifest.json
  style.md
  style.short.md
  idle.png
```

폴더형 캐릭터팩의 manifest에는 `format`, `format_version`이 없어도 됩니다.
이 두 필드는 `.charpack` 아카이브에서만 필수입니다. 폴더형 캐릭터팩을
내보낼 때 앱은 아카이브 형식 필드를 추가하고, 이미지 경로를 아카이브 내부
`images/` 아래로 정규화합니다.

수동 테스트 편의를 위해 `resources/characters/` 폴더 자체에
`manifest.json`이 직접 들어 있는 경우 임시 단일 캐릭터팩으로도 인식합니다.
그래도 일반적으로는 캐릭터 하나당 하위 폴더 하나를 권장합니다.

## 가져오기 정책

메인 앱은 `.charpack` 파일을 사용자 캐릭터 디렉터리로 가져옵니다.

현재 안전장치:

- 아카이브 경로는 상대 경로여야 하며 `..` 또는 백슬래시를 포함할 수 없음
- 빈 아카이브 경로 거부
- 중복 아카이브 경로 거부
- 아카이브 내부 심볼릭 링크 거부
- `manifest.json` 필수
- 아카이브 파일 수 최대 64개
- 압축 해제 후 전체 파일 크기 최대 128 MiB
- 캐릭터 ID는 ASCII 영문자, 숫자, `_`, `-`만 허용
- 캐릭터 ID 비교는 대소문자를 구분하지 않음
- 기본 제공 캐릭터 ID는 예약되어 있으며 가져오기로 덮어쓸 수 없음
- 같은 사용자 캐릭터 ID가 이미 있으면 UI에서 교체 여부를 묻음
- 기존 사용자 캐릭터팩을 교체하면 `.backups` 아래에 백업 생성
- 가져오기 성공 후 가져온 캐릭터를 바로 선택할지 UI에서 묻음

## 내보내기 정책

메인 Settings UI는 사용자 캐릭터팩을 `.charpack`으로 내보냅니다.

현재 동작:

- 기본 제공 캐릭터팩은 Settings에서 내보낼 수 없음
- 없는 선택 상태 이미지는 아카이브에서 생략
- `style.md`는 항상 전체 스타일 파일로 내보냄
- `style.short.md`가 있으면 함께 내보냄
- 이미지 파일은 아카이브 내부 `images/` 아래에 저장
- 대상 파일명에 `.charpack` 확장자가 없으면 자동으로 추가

캐릭터 툴도 `.charpack` 초안을 저장할 수 있습니다. 같은 아카이브 형식을
사용하며, 최소 하나의 `idle` 반응 이미지가 필요합니다.

## 중복 및 버전 정책

캐릭터 ID는 가져오기 충돌을 판단하는 기본 식별자입니다. ID 비교는 대소문자를
구분하지 않으므로 `sample_character`와 `Sample_Character`는 같은 캐릭터
ID로 취급합니다.

같은 사용자 ID가 이미 있는 경우 UI는 기존 버전과 가져올 버전을 보여줍니다.
현재 구현은 semantic version 순서를 강제하지 않습니다. 교체 여부는 사용자가
결정합니다.

## 호환성 메모

- `.charpack` 아카이브에는 `format`, `format_version`이 필요합니다.
- 폴더형 캐릭터팩은 `format`, `format_version`을 생략할 수 있습니다.
- `style.short.md`가 없는 캐릭터팩도 계속 지원됩니다.
- 현재는 이미지 아바타 캐릭터팩만 지원합니다.
- 지원 이미지 형식 외의 바이너리 asset은 현재 캐릭터팩 형식에 포함되지
  않습니다.
