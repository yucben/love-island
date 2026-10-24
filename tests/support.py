"""Process-wide Qt test environment, established before any runtime imports."""
import os
import tempfile

_temporary = tempfile.TemporaryDirectory(prefix="island-tests-")
TEST_ROOT = _temporary.name
os.environ["XDG_CONFIG_HOME"] = TEST_ROOT + "/config"
os.environ["XDG_DATA_HOME"] = TEST_ROOT + "/data"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QSG_RHI_BACKEND"] = "software"

from PySide6.QtGui import QGuiApplication

APPLICATION = QGuiApplication.instance() or QGuiApplication([])
