# Technical Specification Document: Automated Map Imagery AI Analysis System

## 1. Project Overview

### 1.1 Overall Objective
This system aims to establish an automated analysis platform that integrates AI visual recognition (SAM3) and Large Language Models (vLLM) to achieve automatic recognition and comparison of map imagery from different periods, and generate professional qualitative and quantitative analysis reports.

### 1.2 Core Functions
- **Multi-temporal Imagery Acquisition**: Automatically retrieve map imagery from different periods based on longitude, latitude, and range.
- **Intelligent Target Recognition**: Utilize an Agent to convert user natural language instructions into SAM3 prompts to precisely extract masks of target objects.
- **Automated Comparison Analysis**: Combine original images and masks, with vLLM generating analysis reports on object changes (addition, reduction, displacement, deformation).
- **Visualization**: The frontend displays imagery, segmentation results, and the final analysis report in real-time.

---

## 2. Overall Architecture

### 2.1 Logical Architecture
The system adopts a layered architecture design to ensure high modularity and low coupling:

`User Interface (Frontend)` $\longleftrightarrow$ `Backend Engine` $\longleftrightarrow$ `Agent Orchestration Layer` $\longleftrightarrow$ `AI/Data Service Integration Layer`

### 2.2 Module Responsibilities
| Module | Responsibility Description |
| :--- | :--- |
| **Frontend Web Page (Frontend)** | User instruction input, map imagery preview, SAM3 Mask result display, and vLLM report presentation. |
| **Backend Engine** | Receive frontend requests, manage task status, coordinate Agent startup, and handle storage and transmission of imagery files. |
| **Agent Orchestration Layer (Agent)** | Parse user intent $\rightarrow$ Map to professional prompts $\rightarrow$ Drive SAM3 $\rightarrow$ Summarize data for vLLM. |
| **AI Integration Layer (AI Layer)** | Encapsulate API call logic for SAM3 (image segmentation) and vLLM (multimodal analysis). |
| **Data Service Layer (Data Layer)** | Encapsulate map imagery interfaces, responsible for TIF file retrieval, range queries, and cropping. |

---

## 3. Detailed Module Design

### 3.1 Backend Engine
- **Suggested Tech Stack**: Python (FastAPI / Flask)
- **Core Components**:
    - **API Gateway**: Handle frontend RESTful requests.
    - **Task Manager**: Manage the lifecycle of asynchronous analysis tasks.
    - **File Controller**: Manage the conversion between Base64 images and server-side TIF paths.

### 3.2 Agent Orchestration Layer
- **Intent Parsing**: Expand user input terms like "parking lot" into SAM3-recognizable `text_prompt` (e.g., `parking site, parking space`) via a knowledge base or LLM.
- **Workflow Orchestration**:
    1. Trigger imagery cropping $\rightarrow$ 2. Call SAM3 to generate Mask $\rightarrow$ 3. Assemble context $\rightarrow$ 4. Call vLLM to generate report.

### 3.3 AI Integration Layer
#### 3.3.1 SAM3 Adapter
- **Function**: Implement `form-data` submission of images and `text_prompt`.
- **Input**: `img_file`, `text_prompt`.
- **Output**: `combined_mask`, `targets` (including `single_mask` and `bbox`).

#### 3.3.2 vLLM Adapter
- **Function**: Call multimodal models based on the OpenAI protocol.
- **Input**: `original_image` + `mask_image` + `Prompt` (analysis instructions).
- **Output**: Structured text report.

### 3.4 Data Service Layer
- **Interface Encapsulation**:
    - `get_tif_list()` $\rightarrow$ `/tif/list`
    - `get_tif_scope(file_name)` $\rightarrow$ `/tif/scope`
    - `crop_images(lon, lat, radius)` $\rightarrow$ `/tif/crop_all`

---

## 4. Overall Workflow

### 4.1 Imagery Retrieval Workflow
1. **User Input**: Longitude/Latitude $(lon, lat)$, Radius $(radius)$ $\rightarrow$ Frontend submission.
2. **Backend Execution**: Call the `/tif/crop_all` interface.
3. **Result Return**: Retrieve `image_base64` of multi-temporal imagery $\rightarrow$ Frontend rendering and display.

### 4.2 Target Recognition Workflow (Agent $\rightarrow$ SAM3)
1. **User Instruction**: Input "Identify parking lot".
2. **Agent Processing**: Convert "parking lot" $\rightarrow$ `text_prompt: "parking site, parking space"`.
3. **Model Call**: Send the cropped image $\text{Img}_n$ and prompt to SAM3.
4. **Result Extraction**: Retrieve the `single_mask` and `bbox` of the target in each temporal image.

### 4.3 Report Generation Workflow (SAM3 $\rightarrow$ vLLM)
1. **Data Assembly**: Combine $\text{Img}_{t1} + \text{Mask}_{t1}$ with $\text{Img}_{t2} + \text{Mask}_{t2}$.
2. **Analysis Request**: Construct Prompt (e.g., "Compare the two images and their masks to analyze the area change and position shift of the parking lot").
3. **Report Output**: vLLM generates qualitative (change description) and quantitative (estimated area/quantity) reports $\rightarrow$ Frontend presentation.

---

## 5. Interface Definitions

### 5.1 External Service Interfaces (Reference)
| Service | Endpoint | Method | Key Parameters | Key Returns |
| :--- | :--- | :--- | :--- | :--- |
| **Map Imagery** | `/tif/crop_all` | POST | `lon, lat, radius_meters` | `image_base64, save_path` |
| **SAM3** | `/sam3/segment` | POST | `img_file, text_prompt` | `combined_mask, targets` |
| **vLLM** | `/v1/chat/completions`| POST | `model, messages` | `content (Markdown Report)` |

### 5.2 Internal Module Interfaces (Example)
- **Agent $\rightarrow$ SAM3 Adapter**: `generate_mask(image_path, object_name) $\rightarrow$ MaskData`
- **Agent $\rightarrow$ vLLM Adapter**: `analyze_changes(image_set, mask_set) $\rightarrow$ ReportText`

---

## 6. Design Requirements and Constraints

### 6.1 High Modularity
- **Decoupling**: Replacing AI models (e.g., SAM3 $\rightarrow$ SAM4) only requires modifying the corresponding Adapter class, without changing the Agent logic.
- **Independence**: The data service layer and AI computation layer are physically isolated, supporting distributed deployment.

### 6.2 Clear Data Interfaces
- **Unified Format**: Data passed between modules uniformly uses JSON format.
- **Imagery Transmission**: Base64 is used for transmission between frontend and backend, while `save_path` is used for internal backend processing to improve performance.

---

## 7. Environmental Requirements
- **Backend**: Python 3.10+
- **Dependencies**: `openai` (for vLLM), `requests` (for SAM3/TIF API), `FastAPI/Uvicorn`.
- **Network**: Must be able to access `10.12.10.190` (SAM3/TIF) and `10.12.10.161` (vLLM).