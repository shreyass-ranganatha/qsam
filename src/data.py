from qgis.core import (
    QgsReferencedRectangle,
    QgsRectangle,
    QgsCoordinateReferenceSystem)

from pathlib import Path
import sqlite3


class DataStore:
    def __init__(self, path: str = None):
        if path is None:
            path = ":memory:"

        self.db = sqlite3.connect(path)
        self.cursor = self.db.cursor()

        # Create table "rois"
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS rois (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                x_min REAL NOT NULL,
                y_min REAL NOT NULL,
                x_max REAL NOT NULL,
                y_max REAL NOT NULL,
                crs_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.db.commit()

    def insert_roi(self, rect: QgsReferencedRectangle):
        x_min, y_min, x_max, y_max = (
            rect.xMinimum(), rect.yMinimum(),
            rect.xMaximum(), rect.yMaximum(), )

        crs = rect.crs()

        self.cursor.execute(
            "INSERT INTO rois (x_min, y_min, x_max, y_max, crs_id) "
                "VALUES (?, ?, ?, ?, ?)",
            (x_min, y_min, x_max, y_max, crs.authid()))

        self.db.commit()

    def list_rois(self) -> list[QgsReferencedRectangle]:
        self.cursor.execute(
            "SELECT x_min, y_min, x_max, y_max, crs_id FROM rois;")

        rp = self.cursor.fetchall()
        rs = []

        for x_min, y_min, x_max, y_max, crs_id in rp:
            r = QgsRectangle(x_min, y_min, x_max, y_max)
            c = QgsCoordinateReferenceSystem(crs_id)

            rs.append(QgsReferencedRectangle(rectangle=r, crs=c))
        return rs

    def load(self, path: str):
        """Load records from file to this classes object"""

        source_db = sqlite3.connect(path)

        with source_db:
            source_db.backup(self.db)

    def backup(self, path: str):
        """Save records from in-memory db to backup path"""

        backup_db = sqlite3.connect(path)

        with backup_db:
            self.db.backup(backup_db)
