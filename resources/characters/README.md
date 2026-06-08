# User Character Packs

Put additional CharAIface user character pack folders here.

Recommended layout:

```text
resources/characters/your_character_id/
  manifest.json
  style.md
  style.short.md        # optional
  idle.png              # or .jpg/.gif/.apng
```

The app also accepts this folder itself as a temporary single character pack if
`resources/characters/manifest.json` exists, but one subfolder per character is
recommended.

After adding or editing a character pack while the app is running, open
Settings > Character and press **Reload All Character Sets**.

Character IDs are matched case-insensitively. For example,
`sample_character` and `Sample_Character` are treated as the same character ID.

For the `.charpack` archive format, import/export policy, and manifest details,
see [CHARPACK.md](../../CHARPACK.md).

---

# 사용자 캐릭터팩

추가 CharAIface 사용자 캐릭터팩 폴더를 이곳에 넣습니다.

권장 구조:

```text
resources/characters/your_character_id/
  manifest.json
  style.md
  style.short.md        # 선택
  idle.png              # 또는 .jpg/.gif/.apng
```

수동 테스트 편의를 위해 `resources/characters/manifest.json`이 직접 존재하면
이 폴더 자체도 임시 단일 캐릭터팩으로 인식합니다. 다만 일반적으로는 캐릭터
하나당 하위 폴더 하나를 권장합니다.

앱 실행 중 캐릭터팩을 추가하거나 수정했다면 Settings > Character에서
**Reload All Character Sets**를 눌러 다시 불러오세요.

캐릭터 ID 비교는 대소문자를 구분하지 않습니다. 예를 들어
`sample_character`와 `Sample_Character`는 같은 캐릭터 ID로 취급됩니다.

`.charpack` 아카이브 형식, 가져오기/내보내기 정책, manifest 세부 사항은
[CHARPACK.md](../../CHARPACK.md)를 참고하세요.
