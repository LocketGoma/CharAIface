# User Character Sets

Put additional CharAIface character set folders here.

Recommended layout:

```text
resources/characters/your_character_id/
  manifest.json
  style.md
  style.short.md        # optional
  idle.png              # or .jpg/.gif/.apng
```

The app also accepts this folder itself as a temporary single character set if
`resources/characters/manifest.json` exists, but one subfolder per character is
recommended.

After adding or editing a character set while the app is running, open Settings > Character and press **Reload All Character Sets**.

For the `.charpack` archive format, import/export policy, and manifest details,
see [CHARPACK.md](../../CHARPACK.md).
