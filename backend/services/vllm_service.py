from openai import OpenAI
from typing import List, Dict, Any

class VLLMService:
    """vLLM Multimodal Analysis Service Adapter"""
    BASE_URL = "http://10.12.10.161:9998/v1"
    MODEL_NAME = "/home/admin/models/gemma-4-31B-it"
    API_KEY = "token-any-string"

    def __init__(self):
        self.client = OpenAI(
            api_key=self.API_KEY,
            base_url=self.BASE_URL,
        )

    def expand_vocabulary(self, user_input: str) -> tuple[str, Dict[str, str]]:
        """
        Convert Chinese targets entered by the user into English prompt combinations suitable for SAM3, and return a mapping table.
        Supports multi-category input (comma-separated), ensuring each category has an independent mapping.
        Returns: (expanded_prompt, mapping_dict)
        """
        import re
        try:
            # Split input into independent Chinese categories
            zh_categories = [c.strip() for c in re.split(r'[,，\s]+', user_input) if c.strip()]
            if not zh_categories:
                zh_categories = [user_input]

            all_en_keywords = []
            mapping_dict = {}

            system_prompt = (
                "You are a remote sensing image analysis expert. Your task is to convert the Chinese targets the user wants to identify into English keywords most suitable for SAM3 semantic segmentation.\n"
                "Requirements:\n"
                "1. Provide 2-3 relevant English synonyms for each target, separated by English commas.\n"
                "2. Output only English vocabulary, do not include any explanations, serial numbers, or punctuation (except commas).\n"
                "3. If the input contains multiple targets (e.g., 'river, building'), please generate vocabulary for each target and separate the word groups of different targets with a semicolon ';'.\n"
                "Example: Input 'river, building' -> Output 'river, waterway; building, structure'"
            )
            
            response = self.client.chat.completions.create(
                model=self.MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Target: {user_input}"},
                ],
                temperature=0.3,
                max_tokens=200
            )
            raw_content = response.choices[0].message.content.strip()
            
            # Parse results: categories separated by semicolons, synonyms separated by commas
            category_groups = raw_content.split(';')
            for i, group in enumerate(category_groups):
                if i >= len(zh_categories): break
                
                zh_cat = zh_categories[i]
                en_words = [w.strip().lower() for w in group.split(',')]
                for ew in en_words:
                    if ew:
                        all_en_keywords.extend([ew]) # This is slightly wrong, should be to a list
                        mapping_dict[ew] = zh_cat
            
            # Correct the construction of all_en_keywords
            flat_en_list = []
            for group in category_groups:
                flat_en_list.extend([w.strip().lower() for w in group.split(',') if w.strip()])
            
            expanded_prompt = ",".join(flat_en_list)
            if not expanded_prompt:
                expanded_prompt = user_input
            
            return expanded_prompt, mapping_dict
        except Exception as e:
            print(f"vLLM expand_vocabulary Exception: {e}")
            # Simple fallback: use original word as key-value
            fallback_map = {}
            for c in re.split(r'[,，\s]+', user_input):
                if c: fallback_map[c.lower()] = c
            return user_input, fallback_map

    def analyze_changes(self, image_pairs: List[Dict[str, str]], prompt: str) -> str:
        """
        Analyze changes in multi-temporal images and their masks
        :param image_pairs: List containing original images and masks [
            {"original": "base64...", "mask": "base64...", "timestamp": "2023-01"},
            {"original": "base64...", "mask": "base64...", "timestamp": "2024-01"}
        ]
        :param prompt: Analysis instruction
        """
        try:
            content = [{"type": "text", "text": prompt}]
            
            for i, pair in enumerate(image_pairs):
                timestamp = pair.get("timestamp", f"Time {i+1}")
                # Add original image
                content.append({
                    "type": "text", 
                    "text": f"\n--- {timestamp} Original Image ---"
                })
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{pair['original']}"}
                })
                # Add corresponding mask
                content.append({
                    "type": "text", 
                    "text": f"--- {timestamp} Object Mask ---"
                })
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{pair['mask']}"}
                })

            response = self.client.chat.completions.create(
                model=self.MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a professional Geographic Information System (GIS) and remote sensing image analysis expert. Please perform qualitative and quantitative analysis of the changes in target objects based on the provided original images and mask images."},
                    {"role": "user", "content": content},
                ],
                temperature=0.3,
                max_tokens=1024
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"vLLM Service Exception: {e}")
            return f"Analysis failed: {str(e)}"
