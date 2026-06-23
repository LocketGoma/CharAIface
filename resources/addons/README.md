# Add-on Resource Layout

Bundled add-on resources live under one directory per add-on:

```text
resources/addons/<addon_id>/
  __init__.py
  addon.json
  prompt.md
  types.py
  intake.py
  ...
```

`addon.json` is the manifest used by both bundled and external add-on loading.
Prompt files and other inspectable resource files should stay inside the same
add-on directory.

Bundled add-ons that need Python integration keep their add-on-specific code in
the same package as their manifest and resources. Shared loader and registry
infrastructure stays in `shared/addons/`.

External user add-ons are loaded from the per-user `Modules/<addon_id>/`
directory and use the same manifest shape.
