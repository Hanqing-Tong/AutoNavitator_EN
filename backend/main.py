import sys
import os

# Force insert the project root directory at the beginning of sys.path to ensure the backend package is recognized first
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

# Use compatibility imports to support both 'python backend/main.py' and 'python -m backend.main'
try:
    from backend.services.data_service import DataService
    from backend.core.agent import AnalysisAgent
    from backend.services.export_service import ExportService
except ModuleNotFoundError:
    from services.data_service import DataService
    from core.agent import AnalysisAgent
    from services.export_service import ExportService

app = FastAPI(title="AutoNavitator AI Analysis System")

# Allow cross-origin requests for frontend calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
data_service = DataService()
analysis_agent = AnalysisAgent()
export_service = ExportService()


# --- Data Models ---
class CropRequest(BaseModel):
    lon: float
    lat: float
    radius: float
    files: Optional[List[str]] = None

class AnalyzeMaskRequest(BaseModel):
    images: List[dict]  # [{"file_name": "...", "image_base64": "..."}]
    instruction: str    # "Identify parking lot"
    radius: Optional[float] = None

class AnalyzeReportRequest(BaseModel):
    analysis_pairs: List[dict] # [{"timestamp": "...", "original": "...", "mask": "..."}]
    instruction: str
    radius: Optional[float] = None

class ExportRequest(BaseModel):
    report: str
    images: List[dict]

# --- API Implementation ---

@app.get("/api/tif/list")
async def get_tif_list():
    """Get a list of all available TIF files"""
    files = data_service.get_tif_list()
    return {"code": 200, "data": files}

@app.get("/api/tif/scope")
async def get_tif_scope(file_name: str):
    """Query the geographic scope of a single image"""
    scope = data_service.get_tif_scope(file_name)
    if not scope:
        raise HTTPException(status_code=404, detail="File not found or scope unavailable")
    return {"code": 200, "data": scope}

@app.post("/api/crop")
async def crop_images(req: CropRequest):
    """Batch crop multi-temporal images"""
    results = data_service.crop_images(req.lon, req.lat, req.radius, file_list=req.files)
    if not results:
        raise HTTPException(status_code=500, detail="Crop failed or no images found")
    return {"code": 200, "data": results}

@app.post("/api/analyze/mask")
async def analyze_mask(req: AnalyzeMaskRequest):
    """Phase 1: Execute SAM3 target identification"""
    if not req.images:
        raise HTTPException(status_code=400, detail="No images provided for analysis")
    
    try:
        result = analysis_agent.generate_masks(req.images, req.instruction)
        return {"code": 200, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mask generation failed: {str(e)}")

@app.post("/api/analyze/report")
async def analyze_report(req: AnalyzeReportRequest):
    """Phase 2: Execute vLLM report generation"""
    if not req.analysis_pairs:
        raise HTTPException(status_code=400, detail="No analysis pairs provided for report generation")
    
    try:
        report = analysis_agent.generate_report(req.analysis_pairs, req.instruction, radius=req.radius)
        return {"code": 200, "data": {"report": report}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

@app.get("/api/tianditu/reverse")
async def get_tianditu_address(lon: float, lat: float):
    """Call Tianditu reverse geocoding via backend proxy to solve CORS issues"""
    tianditu_key = "e2f89ecfd1959512cb31515a6d16e211"
    # Follow the official standard: use /geocoder path and wrap parameters in postStr JSON string
    import json
    post_data = {"lon": lon, "lat": lat, "ver": 1}
    post_str = json.dumps(post_data)
    url = f"https://api.tianditu.gov.cn/geocoder?postStr={post_str}&type=geocode&tk={tianditu_key}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            if response.status_code != 200:
                return {"code": 500, "detail": f"Tianditu API returned status {response.status_code}"}
            
            res_json = response.json()
            print(f"DEBUG: Tianditu Raw Response: {res_json}") # Diagnostic log
            
            # Convert Tianditu response format (status, formatted_address) to frontend expected format (code, address)
            # Compatibility handling: convert status to string for comparison and add direct check for result field
            status = str(res_json.get("status"))
            result_data = res_json.get("result", {})
            formatted_address = result_data.get("formatted_address") if isinstance(result_data, dict) else None

            if status == "0" or formatted_address:
                address = formatted_address or "Unknown address"
                return {"code": 0, "result": {"address": address}}
            else:
                return {"code": 1, "detail": res_json.get("msg", "Tianditu service did not return a valid address")}
    except Exception as e:
        return {"code": 500, "detail": str(e)}

@app.post("/api/export_report")
async def export_report(req: ExportRequest):
    """Export analysis report as a .docx file"""
    try:
        file_path = export_service.create_docx_report(req.report, req.images)
        return FileResponse(
            path=file_path, 
            filename="AutoNavitator_Analysis_Report.docx", 
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

# Mount the frontend directory to the root path and enable html=True to automatically handle index.html
# Must be placed after all API routes, otherwise it will intercept all requests
app.mount("/", StaticFiles(directory="frontend", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
