from pydantic import BaseModel, Field


class CharacterAvatarConfig(BaseModel):
    type: str = "image"
    images: dict[str, str] = Field(default_factory=dict)


class CharacterThemeConfig(BaseModel):
    base_theme: str = "light"
    palette_override: dict[str, str] = Field(default_factory=dict)


class CharacterPackManifest(BaseModel):
    id: str
    name: str
    localized_names: dict[str, str] = Field(default_factory=dict)
    version: str
    description: str = ""
    author: str = ""

    style_file: str = "style.md"
    style_strength: float = 0.5

    avatar: CharacterAvatarConfig
    theme: CharacterThemeConfig | None = None
