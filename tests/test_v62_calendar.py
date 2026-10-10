"""Verifies binary calendar encoding independently, with synthetic non-player GVAS data."""
import subprocess
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class CalendarLayoutTests(unittest.TestCase):
    def test_synthetic_gvas_roundtrip(self):
        run=subprocess.run([sys.executable,str(ROOT/'tools/smoke_rallyweekend_calendar.py')],
                           cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertIn('SAV binary roundtrip PASS',run.stdout)
        self.assertIn('NoZone',run.stdout)

if __name__ == '__main__':unittest.main()
