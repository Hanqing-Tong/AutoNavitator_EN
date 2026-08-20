import requests
from typing import List, Dict, Any

class DataService:
    """Map imagery data service, encapsulating TIF cropping related interfaces"""
    BASE_URL = "http://10.12.10.190:8002"

    def get_tif_list(self) -> List[str]:
        """Get a list of all TIF files"""
        try:
            response = requests.get(f"{self.BASE_URL}/tif/list")
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 200:
                return data["data"]["tif_files"]
            return []
        except Exception as e:
            print(f"Error fetching TIF list: {e}")
            return []

    def get_tif_scope(self, file_name: str) -> Dict[str, Any]:
        """Query the coordinate range of a single image"""
        try:
            params = {"file_name": file_name}
            response = requests.get(f"{self.BASE_URL}/tif/scope", params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 200:
                return data["data"]
            return {}
        except Exception as e:
            print(f"Error fetching TIF scope: {e}")
            return {}

    def crop_images(self, lon: float, lat: float, radius: float, file_list: list = None) -> List[Dict[str, Any]]:
        """Batch crop TIF files. If file_list is provided, call the single-file crop interface in a loop"""
        try:
            if file_list:
                # External API /tif/crop only supports single-file cropping, so loop calls are required
                results = []
                for file_name in file_list:
                    payload = {
                        "file_name": file_name,
                        "lon": lon,
                        "lat": lat,
                        "radius_meters": radius
                    }
                    response = requests.post(f"{self.BASE_URL}/tif/crop", json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("code") == 200:
                            # Convert the result to a format containing file_name to ensure correct matching on the frontend
                            res_data = data["data"]
                            if isinstance(res_data, dict):
                                res_data["file_name"] = file_name
                                results.append(res_data)
                return results
            else:
                # No file list provided, call the crop-all interface
                payload = {
                    "lon": lon,
                    "lat": lat,
                    "radius_meters": radius
                }
                response = requests.post(f"{self.BASE_URL}/tif/crop_all", json=payload)
                response.raise_for_status()
                data = response.json()
                if data.get("code") == 200:
                    res_data = data["data"]
                    return res_data if isinstance(res_data, list) else [res_data]
                return []
        except Exception as e:
            print(f"Error cropping images: {e}")
            return []
