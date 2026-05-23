from pathlib import Path

from pydantic import BaseModel, Field

from shared.schema.character import CharacterThemeConfig


class CharacterPack(BaseModel):
    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""

    root_dir: Path
    style_path: Path
    style_prompt: str
    style_strength: float = 0.5

    avatar_type: str = "image"
    avatar_images: dict[str, Path] = Field(default_factory=dict)

    theme: CharacterThemeConfig | None = None
    warnings: list[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    def avatar_images_as_str(self) -> dict[str, str]:
        return {
            state: str(path)
            for state, path in self.avatar_images.items()
        }