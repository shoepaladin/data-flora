from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from seattle_schools_dashboard.build import build_site


def main() -> None:
    build_site(PROJECT_ROOT)


if __name__ == "__main__":
    main()
