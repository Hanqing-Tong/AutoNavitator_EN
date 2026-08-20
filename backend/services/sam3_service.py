import requests
import base64
import io
import time
from typing import Dict, Any

class SAM3Service:
    """SAM3 Image Segmentation Service Adapter"""
    API_URL = "http://10.12.10.190:8004/predict/file"
    MAX_RETRIES = 3
    INITIAL_BACKOFF = 1.0  # seconds
    TIMEOUT = 120         # Maximum timeout 120 seconds according to API documentation

    def segment_image(self, image_base64: str, text_prompt: str) -> Dict[str, Any]:
        """
        Call SAM3 interface for image segmentation, including exponential backoff retry mechanism
        :param image_base64: Base64 string of the image (remove data:image/... prefix)
        :param text_prompt: Prompt for the segmentation target
        """
        # Process Base64 string and convert to byte stream
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]
        
        try:
            img_bytes = base64.b64decode(image_base64)
            img_file = io.BytesIO(img_bytes)
            img_file.name = "input.jpg"
        except Exception as e:
            print(f"SAM3 Base64 Decode Error: {e}")
            return {}

        # Prepare request data
        files = {"file": ("input.jpg", img_file, "image/jpeg")}
        data = {
            "texts": text_prompt,
            "return_masks": True,
            "conf": 0.1,  # Lower threshold to increase detection rate
            "return_boxes": True,
            "return_visualization": True
        }

        # Implement exponential backoff retry
        backoff = self.INITIAL_BACKOFF
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                # Need to reset file pointer to the beginning for each attempt
                img_file.seek(0)
                
                response = requests.post(self.API_URL, files=files, data=data, timeout=self.TIMEOUT)
                response.raise_for_status()
                res_json = response.json()

                if res_json.get("success"):
                    return res_json
                else:
                    print(f"SAM3 API Error (Attempt {attempt}): {res_json.get('message', 'Unknown error')}")
                    # If it's a business logic error (rather than a network error), retrying is usually ineffective, return directly
                    return {}

            except (requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout, 
                    requests.exceptions.ChunkedEncodingError) as e:
                print(f"SAM3 Network Error (Attempt {attempt}/{self.MAX_RETRIES}): {e}")
                if attempt == self.MAX_RETRIES:
                    print("SAM3 Service: Max retries reached. Giving up.")
                    break
                
                print(f"Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2  # Exponentially increase wait time
            except Exception as e:
                print(f"SAM3 Unexpected Exception: {e}")
                break
        
        return {}
