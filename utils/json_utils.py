import os
import json
import shutil


def safe_write_json(filepath: str, data: dict) -> None:
    tmp_path = filepath + ".tmp"
    backup_path = filepath + ".bak"
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f)
        if os.path.exists(filepath):
            shutil.copy2(filepath, backup_path)
        os.replace(tmp_path, filepath)
    except Exception as e:
        print(f"Safe write failed: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def safe_read_json(filepath: str) -> dict | None:
    for path in [filepath, filepath + ".bak"]:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r") as f:
                data = json.load(f)
            if path != filepath:
                shutil.copy2(path, filepath)
                print("Recovered state from backup.")
            return data
        except (json.JSONDecodeError, ValueError):
            print(f"Corrupt JSON: {path}")
            continue
    return None
