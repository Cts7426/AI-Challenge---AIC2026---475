import json
import os
import threading
from typing import Dict, Any, List

class ManifestManager:
    def __init__(self, manifest_path: str):
        self.manifest_path = manifest_path
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"processed_zips": [], "processed_videos": {}, "metadata": {}}
        return {"processed_zips": [], "processed_videos": {}, "metadata": {}}

    def save(self):
        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2)

    def is_zip_processed(self, zip_name: str) -> bool:
        with self.lock:
            return zip_name in self.data.get("processed_zips", [])

    def mark_zip_processed(self, zip_name: str):
        with self.lock:
            if zip_name not in self.data["processed_zips"]:
                self.data["processed_zips"].append(zip_name)
                self.save()

    def is_video_processed(self, video_id: str) -> bool:
        with self.lock:
            return video_id in self.data.get("processed_videos", {})

    def mark_video_processed(self, video_id: str, file_size: int, file_md5: str):
        with self.lock:
            if "processed_videos" not in self.data:
                self.data["processed_videos"] = {}
            
            self.data["processed_videos"][video_id] = {
                "size": file_size,
                "md5": file_md5
            }
            self.save()
