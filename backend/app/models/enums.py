"""Shared enums — one definition, used by both SQLAlchemy models and Pydantic schemas."""

import enum


class ResumeOrigin(str, enum.Enum):
    EMAIL = "email"
    FOLDER = "folder"


class MatchTier(str, enum.Enum):
    """Drives the color band in the Candidate Results UI (2.5)."""

    GREAT = "great_match"      # darkest green
    GOOD = "good_match"        # green
    AVERAGE = "average_match"  # orange
    POOR = "poor_match"        # red
    RED_FLAG = "red_flagged"   # darkest red — overrides score-based tier


class PipelineStage(str, enum.Enum):
    """Where a candidate stands in the hiring process for one job — independent of tier."""

    SOURCED = "sourced"            # default — every match starts here
    SCREENED = "screened"
    SUBMITTED = "submitted"        # submitted to client
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    PLACED = "placed"
    DECLINED = "declined"


class FlagColor(str, enum.Enum):
    GREEN = "green"
    RED = "red"


class EmploymentStatus(str, enum.Enum):
    EMPLOYED = "employed"
    UNEMPLOYED = "unemployed"
    ACTIVELY_LOOKING = "actively_looking"
    OPEN_TO_OFFERS = "open_to_offers"
    NOT_LOOKING = "not_looking"
    UNKNOWN = "unknown"


class WorkVisaStatus(str, enum.Enum):
    """US visa types by default; extensible per candidate as free-form 'other' for non-US cases."""

    US_CITIZEN = "us_citizen"
    GREEN_CARD = "green_card"
    H1B = "h1b"
    OPT = "opt"
    STEM_OPT = "stem_opt"
    TN = "tn"
    L1 = "l1"
    E3 = "e3"
    H4_EAD = "h4_ead"
    OTHER = "other"
    UNKNOWN = "unknown"


class EmailProvider(str, enum.Enum):
    GMAIL = "gmail"
    OUTLOOK = "outlook"


class ScanSourceType(str, enum.Enum):
    FOLDER = "folder"
    EMAIL = "email"
