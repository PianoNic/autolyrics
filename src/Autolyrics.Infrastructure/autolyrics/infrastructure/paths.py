from pathlib import Path


class RepositoryPaths:
    """Folders of a source checkout: found by walking up to pyproject.toml, so they do not depend
    on how deep a module sits in the src/<Project>/ layout."""

    @staticmethod
    def root() -> Path:
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / "pyproject.toml").exists():
                return parent
        return Path.cwd()

    @classmethod
    def models(cls) -> Path:
        return cls.root() / "models"

    @classmethod
    def frontend_dist(cls) -> Path:
        return cls.root() / "src" / "Autolyrics.Frontend" / "dist"
