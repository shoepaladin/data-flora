from pathlib import Path
import sys
import json
import os
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seattle_schools_dashboard.build import build_site

# Full build requires downloading NCES + OSPI data from the internet.
# Skip by default; set FULL_BUILD_TEST=1 to run.
_FULL_BUILD = bool(os.environ.get("FULL_BUILD_TEST"))
_skip_no_network = unittest.skipUnless(_FULL_BUILD, "set FULL_BUILD_TEST=1 to run full build test")


@_skip_no_network
class BuildSiteTests(unittest.TestCase):
    def test_build_site_creates_github_pages_output(self) -> None:
        tmp_path = Path(__file__).resolve().parents[1] / ".tmp-test-build" / str(uuid.uuid4())
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            build_site(tmp_path)
            # index.html is no longer generated — it lives in the repo and is
            # uploaded to Pages as-is; only dashboard-data.json is built.
            self.assertFalse((tmp_path / "site" / "index.html").exists())
            self.assertTrue((tmp_path / "site" / "dashboard-data.json").exists())
            self.assertFalse((tmp_path / "data" / "raw" / "nces_placeholder.csv").exists())
            self.assertFalse((tmp_path / "data").exists())
            self.assertFalse((tmp_path / ".tmp-build").exists())

            payload = json.loads((tmp_path / "site" / "dashboard-data.json").read_text(encoding="utf-8"))
            self.assertIn("districts", payload)
            self.assertIn("schools", payload)
            self.assertIn("records", payload)
            self.assertIn("metrics", payload)
            self.assertGreater(len(payload["districts"]), 0)
            self.assertGreater(len(payload["schools"]), 0)
            self.assertGreater(len(payload["records"]), 0)
            self.assertIn("Seattle", [district["name"] for district in payload["districts"]])
        finally:
            import shutil
            shutil.rmtree(tmp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
