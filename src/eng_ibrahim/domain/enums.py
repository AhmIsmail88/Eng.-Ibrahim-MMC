from enum import StrEnum


class Language(StrEnum):
    AR = "ar"
    EN = "en"


class ThemeMode(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class UserRole(StrEnum):
    """أدوار 1.0 وفق ADR-025: Admin ينشئ المستخدمين ويوزع الصلاحية."""

    ADMIN = "admin"
    EDITOR = "editor"
    REPORTS = "reports"
    VIEWER = "viewer"


class LocationType(StrEnum):
    SITE = "site"
    AREA = "area"
    BUILDING = "building"
    ROOM = "room"
    OTHER = "other"
