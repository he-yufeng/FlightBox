"""FlightBox — Black-box flight recorder for AI agents."""

__version__ = "0.1.0"

from flightbox.recorder import FlightRecorder, record
from flightbox.report import build_report, write_report
from flightbox.replayer import replay
from flightbox.store import RecordStore

__all__ = ["FlightRecorder", "record", "replay", "RecordStore", "build_report", "write_report"]
