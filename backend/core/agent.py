from typing import List, Dict, Any, Optional
import numpy as np
import cv2
import base64
from io import BytesIO
from PIL import Image
from backend.services.sam3_service import SAM3Service
from backend.services.vllm_service import VLLMService

class AnalysisAgent:
    """Analysis Agent, responsible for scheduling SAM3 and vLLM to complete the automated analysis workflow"""
    

    def __init__(self):
        self.sam3 = SAM3Service()
        self.vllm = VLLMService()

    def _contour_to_mask(self, shape: List[int], contours: List[List[List[float]]]) -> str:
        """Convert contour points to a base64 mask image"""
        h, w = shape
        mask = np.zeros((h, w), dtype=np.uint8)
        for contour in contours:
            pts = np.array(contour, dtype=np.int32)
            cv2.fillPoly(mask, [pts], 255)
        img = Image.fromarray(mask)
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def _mask_to_contour(self, mask_base64: str) -> List[List[float]]:
        """Convert base64 mask image to contour points [[x, y], ...]"""
        try:
            img_bytes = base64.b64decode(mask_base64)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if img is None:
                return []
            
            # Find the largest contour
            contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return []
            
            # Take the contour with the largest area
            main_contour = max(contours, key=cv2.contourArea)
            # Convert to [[x, y], ...] format
            points = main_contour.reshape(-1, 2).astype(float).tolist()
            return points
        except Exception as e:
            print(f"Mask to Contour Error: {e}")
            return []

    def _expand_prompt(self, user_input: str) -> tuple[str, Dict[str, str]]:
        """Convert user instructions into SAM3 prompts using LLM dynamic expansion and return a mapping table"""
        print(f"Agent: Dynamically generating prompts for target [{user_input}]...")
        return self.vllm.expand_vocabulary(user_input)

    def generate_masks(self, images: List[Dict[str, Any]], user_instruction: str) -> Dict[str, Any]:
        """
        Phase 1: Generate Mask results
        :param images: List of cropped images [{"file_name": "...", "image_base64": "..."}]
        :param user_instruction: Target to identify entered by the user
        :return: Dictionary containing mask_results and analysis_pairs
        """
        import re
        # 0. Sort the image list by filename in ascending order
        images = sorted(images, key=lambda x: x.get("file_name", ""))
        
        # 1. Uniformly generate prompts and mapping table
        sam3_prompt, label_mapping = self._expand_prompt(user_instruction)
        keywords = [k.strip() for k in re.split(r'[,，\s]+', user_instruction) if k.strip()]
        if not keywords:
            keywords = [user_instruction]

        analysis_pairs = []
        mask_results = []

        print(f"Agent: [Phase 1] Starting to process target [{user_instruction}], mapped prompt: [{sam3_prompt}]")

        for img_info in images:
            file_name = img_info.get("file_name", "unknown")
            img_base64 = img_info.get("image_base64", "")
            
            # Dynamically obtain actual image dimensions to avoid using default [1024, 1024]
            try:
                # Remove potential data:image/...;base64, prefix
                pure_b64 = img_base64.split(',')[-1]
                img_bytes = base64.b64decode(pure_b64)
                nparr = np.frombuffer(img_bytes, np.uint8)
                temp_img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
                if temp_img is not None:
                    h, w = temp_img.shape[:2]
                    actual_shape = [h, w]
                else:
                    actual_shape = [1024, 1024]
            except Exception as e:
                print(f"Agent: Failed to get image dimensions {e}, using default value")
                actual_shape = [1024, 1024]

            print(f"Agent: Generating Mask for {file_name}... (Size: {actual_shape[1]}x{actual_shape[0]})")
            sam_res = self.sam3.segment_image(img_base64, sam3_prompt)
            
            # Debug log: Print SAM3 response results
            if not sam_res:
                print(f"Agent: {file_name} SAM3 interface returned empty")
            else:
                print(f"Agent: {file_name} SAM3 response successful, number of instances: {sum(len(c.get('instances', [])) for c in sam_res.get('results', []))}")

            # Prefer using the shape returned by the interface, otherwise use the actual shape detected earlier
            img_shape = sam_res.get("image_shape", actual_shape) if sam_res else actual_shape
            all_contours = []
            processed_targets = []
            combined_mask = ""

            # Try first identification (using LLM expanded prompts)
            sam_res = self.sam3.segment_image(img_base64, sam3_prompt)
            
            # If no result from the first attempt, try falling back to original keywords
            if not sam_res or not sam_res.get("results") or sum(len(c.get('instances', [])) for c in sam_res.get('results', [])) == 0:
                print(f"Agent: {file_name} expanded prompt did not detect anything, trying original keyword fallback...")
                fallback_prompt = ",".join(keywords)
                sam_res = self.sam3.segment_image(img_base64, fallback_prompt)

            if sam_res and "results" in sam_res:
                # Iterate through the results structure of the new interface
                for cat_res in sam_res.get("results", []):
                    category = cat_res.get("category", "unknown")
                    instances = cat_res.get("instances", [])
                    
                    for inst in instances:
                        # Convert from mask to contour points
                        mask_b64 = inst.get("mask", "")
                        segmentation = self._mask_to_contour(mask_b64)
                        if not segmentation:
                            continue
                        
                        all_contours.append(segmentation)
                        
                        # Generate an independent Mask for each instance
                        inst_mask = self._contour_to_mask(img_shape, [segmentation])
                        
                        # Convert absolute coordinates to normalized coordinates [0, 1] to ensure frontend rendering alignment
                        h, w = img_shape
                        normalized_segmentation = [[p[0] / w, p[1] / h] for p in segmentation]
                        
                        # Label mapping
                        lower_cat = category.lower()
                        final_label = label_mapping.get(lower_cat, category)
                        
                        if final_label == category:
                            for key, val in label_mapping.items():
                                if key in lower_cat:
                                    final_label = val
                                    break
                        
                        processed_targets.append({
                            "label": final_label,
                            "mask_base64": inst_mask,
                            "segmentation": normalized_segmentation,
                            "bbox": inst.get("bbox"),
                            "confidence": inst.get("confidence"),
                            "color": inst.get("color")
                        })
                
                # Generate combined Mask
                combined_mask = self._contour_to_mask(img_shape, all_contours)
            else:
                # When failed or no results, generate a completely black mask image
                combined_mask = self._contour_to_mask(img_shape, [])
                print(f"Agent: {file_name} target not detected or interface call failed, using empty mask")

            mask_results.append({
                "file_name": file_name,
                "combined_mask": combined_mask,
                "targets": processed_targets
            })
            analysis_pairs.append({
                "timestamp": file_name,
                "original": img_base64,
                "mask": combined_mask
            })

        return {
            "mask_results": mask_results,
            "analysis_pairs": analysis_pairs
        }

    def generate_report(self, analysis_pairs: List[Dict[str, Any]], user_instruction: str, radius: Optional[float] = None) -> str:
        """
        Phase 2: Generate analysis report
        :param analysis_pairs: Pairs containing original images and Masks [{"timestamp": "...", "original": "...", "mask": "..."}]
        :param user_instruction: Target to identify entered by the user
        :param radius: Cropping radius
        :return: Generated Markdown report
        """
        if not analysis_pairs:
            raise ValueError("No analysis pairs provided, cannot generate report.")

        print("Agent: [Phase 2] Calling vLLM to generate comparison report...")
        
        scale_info = f"The cropping radius of the current imagery is {radius} meters." if radius else "No specific physical scale information provided."
        
        vllm_prompt = (
            f"User requested analysis target: {user_instruction}.\n"
            f"Spatial scale reference: {scale_info}\n"
            "I have provided original images from different periods and their corresponding target Mask images.\n"
            "Please compare these images and analyze the qualitative changes of the target in detail (e.g., additions, disappearances, shape changes, position shifts),\n"
            "and perform quantitative estimations combined with the spatial scale (e.g., estimating the specific area, length, increase/decrease in quantity of the target).\n"
            "Analyze the target Mask images; do not perform quantitative estimations for incorrectly segmented parts.\n"
            "Please provide a final conclusion: whether there are obvious changes in the target imagery in the images. Please answer with 'Yes' or 'No', and the conclusion should exclude mask recognition errors.\n\n"
            "【Output Requirements】:\n"
            "1. **Strictly forbid any placeholders or guide symbols**: It is absolutely forbidden to output symbols such as '####', '###', '[value]', 'X.X', or '...'. Whether as a placeholder or a calculation guide (e.g., '#### ≈ ...' is forbidden), they are not allowed. You must directly output specific values or LaTeX formulas.\n"
            "2. **Mandatory LaTeX Format**: All mathematical formulas, calculation processes, physical quantities, and units must be wrapped in LaTeX format. For example: Correct: $40.6\\text{m} \\times 4.0\\text{m} \\approx 162.4\\text{m}^2$, Incorrect: 40.6m * 4.0m = 162.4m2.\n"
            "3. **Example Reference**:\n"
            "   - Correct: The target length is approximately $45\\text{m}$, the width is approximately $10\\text{m}$, and the estimated area is $450\\text{m}^2$.\n"
            "   - Incorrect: Area estimation: #### ≈ $40\\text{m} \\times 5\\text{m} = 200\\text{m}^2$ (Forbidden to use #### guide).\n"
            "   - Incorrect: The target length is approximately ####, and the width is approximately ####.\n"
            "4. Please output in a professional report format."
        )
        
        return self.vllm.analyze_changes(analysis_pairs, vllm_prompt)
