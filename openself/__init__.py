"""openself: read, write, index, check and version an OpenSelf profile (see ../SPEC.md).

Standard library only, so any tool can vendor it or use it from a git submodule.
"""

from .model import Entry, Flag, Profile, Section, find, flags, load_profile, sections, version  # noqa: F401
from .schema import SCHEMA_VERSION  # noqa: F401

__version__ = "1.0.0"
