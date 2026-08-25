"""INI-based i18n. Code must use dotted keys (`section.key`), never raw user strings."""

from __future__ import annotations

import configparser
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES = ("ru", "en")


def _candidate_dirs() -> list[Path]:
    here = Path(__file__).resolve()
    found: list[Path] = [Path.cwd() / "locales"]
    for parent in here.parents:
        found.append(parent / "locales")
    return found


class I18n:
    def __init__(self, locales_dir: Path | None = None, default_locale: str = "ru") -> None:
        self.default_locale = default_locale if default_locale in SUPPORTED_LOCALES else "ru"
        self._catalogs: dict[str, configparser.RawConfigParser] = {}
        directory = locales_dir or next((path for path in _candidate_dirs() if path.is_dir()), None)
        if directory is None:
            raise FileNotFoundError("locales directory not found")
        for locale in SUPPORTED_LOCALES:
            parser = configparser.RawConfigParser()
            parser.optionxform = str
            path = directory / f"{locale}.ini"
            read = parser.read(path, encoding="utf-8")
            if not read:
                logger.warning("locale file missing: %s", path)
            self._catalogs[locale] = parser

    def values_for(self, key: str) -> frozenset[str]:
        """All locale strings for a key. Used to match reply-keyboard labels."""
        return frozenset(self.get(locale, key) for locale in SUPPORTED_LOCALES)

    def matches(self, text: str | None, key: str) -> bool:
        if not text:
            return False
        return text.strip() in self.values_for(key)

    def get(self, locale: str, key: str, **kwargs: object) -> str:
        section, _, option = key.partition(".")
        text = self._lookup(locale, section, option)
        if text is None and locale != self.default_locale:
            text = self._lookup(self.default_locale, section, option)
        if text is None:
            logger.warning("missing locale key %s for %s", key, locale)
            text = key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
        return text

    def _lookup(self, locale: str, section: str, option: str) -> str | None:
        catalog = self._catalogs.get(locale)
        if catalog is None or not catalog.has_option(section, option):
            return None
        return catalog.get(section, option).replace("\\n", "\n")
