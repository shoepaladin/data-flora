from pathlib import Path

from seattle_schools_dashboard.build import build_site

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent.parent / "seattle_area_school_dashboard"
    print(f"Building dashboard at {project_root} ...")
    build_site(project_root)
    print("Done. Output written to site/")
