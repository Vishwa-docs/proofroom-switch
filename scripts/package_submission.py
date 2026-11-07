"""Create a source-and-demo packet from tracked files, excluding local secrets."""

import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "submission" / "proofroom-submission.zip"


def main():
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
    files = [Path(item.decode()) for item in tracked if item]
    forbidden = {".env", "state.json", ".switch-cursors.json"}
    if any(path.name in forbidden or "raw" in path.parts for path in files):
        raise SystemExit("Refusing to package local credentials, state, or raw recordings.")
    if Path("demo/proofroom-switch-demo.mp4") not in files:
        raise SystemExit("Demo video is missing from tracked files.")
    with zipfile.ZipFile(DEST, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(ROOT / path, Path("proofroom") / path)
    print(f"Packaged {len(files)} files: {DEST}")


if __name__ == "__main__":
    main()
