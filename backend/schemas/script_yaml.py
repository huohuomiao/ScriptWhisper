from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScriptLineType = Literal["action", "dialogue", "transition", "note"]


class ProjectInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1)
    version: str = Field(default="1.0", min_length=1)
    genre: str | None = None
    logline: str | None = None
    source: str | None = None


class Character(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(..., min_length=1)
    role: str | None = None
    description: str | None = None


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(..., min_length=1)
    description: str | None = None


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    title: str = Field(..., min_length=1)
    location_id: str = Field(..., min_length=1)
    characters: list[str] = Field(default_factory=list)
    summary: str | None = None


class ScriptLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., min_length=1)
    type: ScriptLineType
    content: str = Field(..., min_length=1)
    character_id: str | None = None

    @model_validator(mode="after")
    def validate_dialogue_character(self) -> "ScriptLine":
        if self.type == "dialogue" and not self.character_id:
            raise ValueError("dialogue script lines require character_id")
        return self


class ScriptYAML(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectInfo
    characters: list[Character] = Field(..., min_length=1)
    locations: list[Location] = Field(..., min_length=1)
    scenes: list[Scene] = Field(..., min_length=1)
    script: list[ScriptLine] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_integrity(self) -> "ScriptYAML":
        character_ids = _unique_ids(self.characters, "characters")
        location_ids = _unique_ids(self.locations, "locations")
        scene_ids = _unique_ids(self.scenes, "scenes")

        scene_characters = {scene.id: set(scene.characters) for scene in self.scenes}

        for scene in self.scenes:
            if scene.location_id not in location_ids:
                raise ValueError(f"scene '{scene.id}' references unknown location_id '{scene.location_id}'")

            unknown_characters = sorted(set(scene.characters) - character_ids)
            if unknown_characters:
                raise ValueError(
                    f"scene '{scene.id}' references unknown character ids: {', '.join(unknown_characters)}"
                )

        script_scene_ids: set[str] = set()
        for line in self.script:
            if line.scene_id not in scene_ids:
                raise ValueError(f"script line references unknown scene_id '{line.scene_id}'")

            script_scene_ids.add(line.scene_id)

            if line.character_id and line.character_id not in character_ids:
                raise ValueError(f"script line references unknown character_id '{line.character_id}'")

            if line.character_id and line.character_id not in scene_characters[line.scene_id]:
                raise ValueError(
                    f"character '{line.character_id}' is not listed in scene '{line.scene_id}' characters"
                )

        missing_script = [scene.id for scene in self.scenes if scene.id not in script_scene_ids]
        if missing_script:
            raise ValueError(f"scenes missing script lines: {', '.join(missing_script)}")

        return self


def _unique_ids(items: list[Character] | list[Location] | list[Scene], label: str) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()

    for item in items:
        if item.id in seen:
            duplicates.add(item.id)
        seen.add(item.id)

    if duplicates:
        raise ValueError(f"{label} contains duplicate ids: {', '.join(sorted(duplicates))}")

    return seen
