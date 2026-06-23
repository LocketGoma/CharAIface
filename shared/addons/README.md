# Shared Add-on Infrastructure

Common add-on infrastructure stays at this package root:

```text
shared/addons/base.py
shared/addons/external.py
shared/addons/manifest_loader.py
shared/addons/registry.py
```

Bundled add-on implementations and resources live together in one package per
add-on:

```text
resources/addons/<addon_id>/
  __init__.py
  addon.json
  prompt.md
```

Keep add-on-specific code out of this package unless it is needed by more than
one add-on.
