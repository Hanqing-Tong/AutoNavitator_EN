const API_BASE = "/api";
const TIANDITU_KEY = "tianditu_key"; // For backend proxy
const BROWSER_TK = "browser_tk";   // For frontend map
let map = null;
let currentMarker = null;
let croppedImages = [];
let currentRadius = null;
let currentReportMarkdown = "";
let currentMaskResults = [];
let globalCategoryToColor = {};
let globalColorUsage = new Set();

async function loadTifList() {
    const container = document.getElementById('tif-list-container');
    if (!container) return;
    try {
        const response = await fetch(`${API_BASE}/tif/list`);
        const result = await response.json();
        
        if (result.code === 200) {
            const files = result.data;
            if (files.length === 0) {
                container.innerHTML = '<div class="loading-text">No available imagery files</div>';
                return;
            }
            
            container.innerHTML = '';
            files.forEach(fileName => {
                const item = document.createElement('div');
                item.className = 'tif-item';
                item.innerHTML = `
                    <input type="checkbox" value="${fileName}" checked>
                    <span>${fileName}</span>
                `;
                item.onclick = (e) => {
                    if (e.target !== item.querySelector('input')) {
                        const cb = item.querySelector('input');
                        cb.checked = !cb.checked;
                    }
                };
                container.appendChild(item);
            });
        } else {
            container.innerHTML = '<div class="loading-text">Loading failed, please check the backend service</div>';
        }
    } catch (error) {
        console.error('Error loading TIF list:', error);
        container.innerHTML = '<div class="loading-text">Network error, unable to connect to the server</div>';
    }
}

function toggleAllTifs() {
    const checkboxes = document.querySelectorAll('.tif-item input[type="checkbox"]');
    const btn = document.getElementById('toggle-all-btn');
    if (!checkboxes.length) return;
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    
    checkboxes.forEach(cb => cb.checked = !allChecked);
    btn.textContent = allChecked ? 'Select All' : 'Deselect All';
}

// DOM elements
const elements = {
    lon: () => document.getElementById('lon'),
    lat: () => document.getElementById('lat'),
    radius: () => document.getElementById('radius'),
    btnCrop: () => document.getElementById('btn-crop'),
    imageGallery: () => document.getElementById('image-gallery'),
    analysisSection: () => document.getElementById('analysis-section'),
    instruction: () => document.getElementById('instruction'),
    btnAnalyze: () => document.getElementById('btn-analyze'),
    maskGallery: () => document.getElementById('mask-gallery'),
    reportContainer: () => document.getElementById('report-container'),
    reportContent: () => document.getElementById('report-content'),
    loading: () => document.getElementById('analysis-loading'),
    tiandituMap: () => document.getElementById('tianditu-map'),
    placeName: () => document.getElementById('place-name')
};

/**
 * Initialize interactive Tianditu map
 */
function initTiandituMap() {
    const mapEl = elements.tiandituMap();
    if (!mapEl) return;

    // Initialize map, set center point to default value
    map = L.map('tianditu-map', {
        zoomControl: false,
        attributionControl: false
    }).setView([30.017839, 120.725088], 15);

    // Add Tianditu satellite imagery layer
    L.tileLayer(`https://t0.tianditu.gov.cn/img_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=img&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=${BROWSER_TK}`, {
        maxZoom: 18,
        minZoom: 1
    }).addTo(map);

    // Bind map click event: select point to get longitude and latitude
    map.on('click', function(e) {
        const { lat, lng } = e.latlng;

        // 1. Update input field values
        elements.lon().value = lng.toFixed(6);
        elements.lat().value = lat.toFixed(6);

        // 2. Center map: move clicked point to center
        map.panTo([lat, lng]);

        // 3. Update visual marker (Marker)
        if (currentMarker) {
            map.removeLayer(currentMarker);
        }
        currentMarker = L.marker([lat, lng]).addTo(map);
    });
}

/**
 * Update Tianditu map position and reverse geocoding for place name
 */
async function updateTiandituMap(lon, lat) {
    const nameEl = elements.placeName();
    if (!nameEl) return;

    // 1. Smoothly pan map to target position
    if (map) {
        map.flyTo([lat, lon], 16);
    }

    // 2. Perform reverse geocoding via backend proxy
    nameEl.innerText = "Querying place name...";
    try {
        const response = await fetch(`${API_BASE}/tianditu/reverse?lon=${lon}&lat=${lat}`);
        const data = await response.json();
        
        if (data.code === 0 && data.result && data.result.address) {
            nameEl.innerText = data.result.address;
        } else if (data.detail) {
            nameEl.innerText = `Query failed: ${data.detail}`;
        } else {
            nameEl.innerText = "No specific place name found";
        }
    } catch (error) {
        console.error("Tianditu proxy error:", error);
        nameEl.innerText = "Place name query service unavailable";
    }
}

// Initialization function
function init() {
    initTiandituMap();
    const btnCrop = elements.btnCrop();
    if (btnCrop) {
        btnCrop.onclick = async () => {
            const selectedFiles = Array.from(document.querySelectorAll('.tif-item input:checked'))
                                       .map(cb => cb.value);

            const radiusValue = parseFloat(elements.radius().value);
            currentRadius = radiusValue;

            const payload = {
                lon: parseFloat(elements.lon().value),
                lat: parseFloat(elements.lat().value),
                radius: radiusValue,
                files: selectedFiles.length > 0 ? selectedFiles : null
            };

            btnCrop.disabled = true;
            btnCrop.innerText = "Cropping...";
            elements.imageGallery().innerHTML = "";

            try {
                // Synchronously update Tianditu map
                updateTiandituMap(payload.lon, payload.lat);

                const response = await fetch(`${API_BASE}/crop`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await response.json();

                if (result.code === 200) {
                    // Sort cropping results by filename in ascending order to ensure T1 is before T2 (earlier date on the left)
                    croppedImages = result.data.sort((a, b) => {
                        const nameA = a.file_name || "";
                        const nameB = b.file_name || "";
                        return nameA.localeCompare(nameB);
                    });
                    renderGallery(croppedImages, elements.imageGallery(), "Original Image");
                    elements.analysisSection().style.display = "block";
                    elements.analysisSection().scrollIntoView({ behavior: 'smooth' });
                } else {
                    alert("Cropping failed: " + (result.detail || "Unknown error"));
                }
            } catch (error) {
                console.error("Error:", error);
                alert("Network request failed, please ensure the backend service is running");
            } finally {
                btnCrop.disabled = false;
                btnCrop.innerText = "Batch Crop Imagery";
            }
        };
    }

    const btnExport = document.getElementById('btn-export');
    if (btnExport) {
        btnExport.onclick = async () => {
            if (!currentReportMarkdown) {
                alert("No report available for export");
                return;
            }

            btnExport.disabled = true;
            btnExport.innerText = "Exporting...";

            try {
                const response = await fetch(`${API_BASE}/export_report`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        report: currentReportMarkdown,
                        images: currentMaskResults
                    })
                });

                if (!response.ok) throw new Error("Server export failed");

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = "AutoNavitator_Analysis_Report.docx";
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } catch (error) {
                console.error("Export error:", error);
                alert("Failed to export report, please check the backend service");
            } finally {
                btnExport.disabled = false;
                btnExport.innerText = "Export DOCX Report";
            }
        };
    }

    const btnAnalyze = elements.btnAnalyze();
    if (btnAnalyze) {
        btnAnalyze.onclick = async () => {
            // Reset global color mapping to ensure reallocation for each analysis
            globalCategoryToColor = {};
            globalColorUsage = new Set();

            const instruction = elements.instruction().value.trim();
            if (!instruction) {
                alert("Please enter the target to identify (e.g., parking lot)");
                return;
            }

            const maskPayload = {
                images: croppedImages,
                instruction: instruction,
                radius: currentRadius
            };

            btnAnalyze.disabled = true;
            elements.loading().style.display = "block";
            elements.loading().innerText = "Identifying targets...";
            elements.maskGallery().innerHTML = "";
            elements.reportContainer().style.display = "none";

            try {
                // --- Phase 1: Request Mask ---
                const maskController = new AbortController();
                const maskTimeoutId = setTimeout(() => maskController.abort(), 300000);

                const maskResponse = await fetch(`${API_BASE}/analyze/mask`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(maskPayload),
                    signal: maskController.signal
                });
                clearTimeout(maskTimeoutId);
                const maskResult = await maskResponse.json();

                if (maskResult.code !== 200) {
                    throw new Error("Mask 生成失败: " + (maskResult.detail || "未知错误"));
                }

                const { mask_results, analysis_pairs } = maskResult.data;
                
                // Immediately render Mask results
                currentMaskResults = mask_results.map(item => {
                    const originalImgData = croppedImages.find(crop => crop.file_name === item.file_name);
                    return {
                        file_name: item.file_name,
                        original_base64: originalImgData ? originalImgData.image_base64 : null,
                        mask_base64: item.combined_mask,
                        targets: item.targets || []
                    };
                }).sort((a, b) => (a.file_name || "").localeCompare(b.file_name || ""));

                renderGallery(currentMaskResults, elements.maskGallery(), "Target Identification");

                // --- Phase 2: Request Report ---
                elements.loading().innerText = "Target identification complete, generating analysis report...";
                
                const reportPayload = {
                    analysis_pairs: analysis_pairs,
                    instruction: instruction,
                    radius: currentRadius
                };

                const reportController = new AbortController();
                const reportTimeoutId = setTimeout(() => reportController.abort(), 300000);

                const reportResponse = await fetch(`${API_BASE}/analyze/report`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(reportPayload),
                    signal: reportController.signal
                });
                clearTimeout(reportTimeoutId);
                const reportResult = await reportResponse.json();

                if (reportResult.code === 200) {
                    const report = reportResult.data.report;
                    currentReportMarkdown = report;
                    elements.reportContent().innerHTML = marked.parse(report);
                    
                    if (typeof renderMathInElement === 'function') {
                        renderMathInElement(elements.reportContent(), {
                            delimiters: [
                                {left: '$$', right: '$$', display: true},
                                {left: '$', right: '$', display: false},
                                {left: '\\(', right: '\\)', display: false},
                                {left: '\\[', right: '\\]', display: true}
                            ],
                            throwOnError: false
                        });
                    }
                    elements.reportContainer().style.display = "block";
                } else {
                    throw new Error("Report generation failed: " + (reportResult.detail || "Unknown error"));
                }

            } catch (error) {
                console.error("Analysis Error:", error);
                if (error.name === 'AbortError') {
                    alert("Request timed out, please check backend logs or try again later.");
                } else if (error instanceof TypeError) {
                    alert("Network connection anomaly, please ensure the backend service is running.");
                } else {
                    alert(error.message);
                }
            } finally {
                btnAnalyze.disabled = false;
                elements.loading().style.display = "none";
                elements.loading().innerText = "Analyzing..."; // 重置默认文本
            }
        };
    }

    loadTifList();
}

document.addEventListener('DOMContentLoaded', init);


// Full-screen preview function
function openLightbox(baseSrc, overlaySrc = null) {
    const lightbox = document.getElementById('image-lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    const compContainer = document.getElementById('comparison-container');
    const compBase = document.getElementById('comp-img-base');
    const compOverlay = document.getElementById('comp-img-overlay');

    if (!lightbox) return;

        if (overlaySrc) {
            // Overlay mode
            lightboxImg.style.display = 'none';
        compContainer.style.display = 'block';
        compBase.src = baseSrc;
        compOverlay.src = overlaySrc;
        } else {
            // Single image mode
            compContainer.style.display = 'none';
        lightboxImg.style.display = 'block';
        lightboxImg.src = baseSrc;
    }
    
    lightbox.style.display = 'flex';
}

// Close modal
function closeLightbox(e) {
    // Close if background area or close button is clicked
    if (e.target.id === 'image-lightbox' || e.target.id === 'close-lightbox') {
        document.getElementById('image-lightbox').style.display = 'none';
    }
}

// Color palette, alpha value set to 0.2 for mask visibility on map
const MASK_COLORS = [
    'rgba(255, 0, 0, 0.2)',    // 红
    'rgba(0, 255, 0, 0.2)',    // 绿
    'rgba(0, 0, 255, 0.2)',    // 蓝
    'rgba(255, 255, 0, 0.2)',  // 黄
    'rgba(255, 0, 255, 0.2)',  // 品红
    'rgba(0, 255, 255, 0.2)',  // 青
    'rgba(255, 165, 0, 0.2)',  // 橙
    'rgba(128, 0, 128, 0.2)',  // 紫
];

/**
 * Use Canvas to render multi-color Mask overlay (based on semantic classification)
 */
async function createMultiColorMaskCanvas(originalSrc, targets, instruction = "") {
    return new Promise((resolve) => {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        const baseImg = new Image();
        
        baseImg.onload = async () => {
            canvas.width = baseImg.width;
            canvas.height = baseImg.height;
            
            // 1. Draw base map
            ctx.drawImage(baseImg, 0, 0);
            
             // --- Semantic color allocation logic ---
             // 1. Extract keywords from user instructions (as baseline labels)
             const keywords = instruction.split(/[,，\s]+/).filter(k => k.trim());

             // Pre-allocate keyword colors (executed only on first render or when global table is empty, or ensure keyword priority on each call)
             keywords.forEach((kw, idx) => {
                 const lowerKw = kw.toLowerCase();
                 if (!globalCategoryToColor[lowerKw]) {
                     // Find a color that has not been used yet
                     let colorIdx = 0;
                     while (globalColorUsage.has(MASK_COLORS[colorIdx % MASK_COLORS.length])) {
                         colorIdx++;
                     }
                     const color = MASK_COLORS[colorIdx % MASK_COLORS.length];
                     globalCategoryToColor[lowerKw] = color;
                     globalColorUsage.add(color);
                 }
             });

                // Helper function: trust labels passed from backend
                const resolveLabel = (aiLabel) => {
                    if (!aiLabel || aiLabel === "Unknown Target") {
                        return keywords.length > 0 ? keywords[0] : "Unknown Target";
                    }
                    return aiLabel; // Directly use semantic labels returned from backend
                };

                // Helper function: get target color and record category mapping
                const getSemanticColor = (resolvedLabel) => {
                    const lowerLabel = resolvedLabel.toLowerCase();
                    
                    // If already in global mapping table, return directly
                    if (globalCategoryToColor[lowerLabel]) {
                        return globalCategoryToColor[lowerLabel];
                    }

                    // If it's a new label generated by AI, allocate new color and record in global table
                  let colorIdx = 0;
                  while (globalColorUsage.has(MASK_COLORS[colorIdx % MASK_COLORS.length])) {
                      colorIdx++;
                  }
                  const newColor = MASK_COLORS[colorIdx % MASK_COLORS.length];
                  globalCategoryToColor[lowerLabel] = newColor;
                  globalColorUsage.add(newColor);
                  
                  return newColor;
              };

                const finalCategoryMap = {}; // Used to store { final display label: color } actually appearing in this image

                // 2. Draw target contours one by one (use vector drawing instead of Mask images)
              console.log(`Rendering ${targets.length} targets for image...`);
               for (let i = 0; i < targets.length; i++) {
                   const target = targets[i];
                   const segmentation = target.segmentation;
                   if (!segmentation || !Array.isArray(segmentation) || segmentation.length === 0) continue;
                   
                   const rawLabel = target.label || "Unknown Target";
                   const resolvedLabel = resolveLabel(rawLabel);
                  const color = getSemanticColor(resolvedLabel);
                  finalCategoryMap[resolvedLabel] = color;
                 
                    // Coordinate scale detection: determine if normalized coordinates (0-1)
                    // If x or y of the first point is within [0, 1] and image size is large, consider it normalized coordinates
                  const isNormalized = (segmentation[0][0] <= 1.0 && segmentation[0][1] <= 1.0) && 
                                      (canvas.width > 100 || canvas.height > 100);
                  
                  if (i === 0) {
                      console.log(`Target 0: label=${resolvedLabel}, points=${segmentation.length}, isNormalized=${isNormalized}, firstPoint=[${segmentation[0]}]`);
                  }

                    // Use Canvas path to draw filled polygon
                  ctx.fillStyle = color;
                  ctx.beginPath();
                  
                  const startX = isNormalized ? segmentation[0][0] * canvas.width : segmentation[0][0];
                  const startY = isNormalized ? segmentation[0][1] * canvas.height : segmentation[0][1];
                  ctx.moveTo(startX, startY);
                  
                  for (let j = 1; j < segmentation.length; j++) {
                      const px = isNormalized ? segmentation[j][0] * canvas.width : segmentation[j][0];
                      const py = isNormalized ? segmentation[j][1] * canvas.height : segmentation[j][1];
                      ctx.lineTo(px, py);
                  }
                  ctx.closePath();
                  ctx.fill();
              }
            resolve({
                imageSrc: canvas.toDataURL('image/png'),
                categoryMap: finalCategoryMap
            });
        };
        baseImg.src = originalSrc;
    });
}

// General image rendering function
async function renderGallery(images, container, label) {
    container.innerHTML = ''; // Clear container
    for (const img of images) {
        const div = document.createElement('div');
        div.className = 'img-item';
        
        let base64Data = img.image_base64 || img.mask_base64;
        if (!base64Data) {
            console.error(`Missing image data for ${img.file_name}`);
            continue;
        }

        // Remove whitespace or newline characters that may cause loading failure
        base64Data = base64Data.trim();

        const src = base64Data.startsWith('data:') 
                    ? base64Data 
                    : `data:image/png;base64,${base64Data}`;

        let content;
        if (label === "Target Identification") {
            // Mask rendering mode: use multi-color Canvas rendering
            const originalImgData = croppedImages.find(item => item.file_name === img.file_name);
            const originalSrc = originalImgData && originalImgData.image_base64.startsWith('data:') 
                                 ? originalImgData.image_base64 
                                 : (originalImgData ? `data:image/png;base64,${originalImgData.image_base64}` : src);

            const targets = img.targets || [];
            const instruction = elements.instruction().value;
            const { imageSrc: renderedSrc, categoryMap } = await createMultiColorMaskCanvas(originalSrc, targets, instruction);
            
            const canvasImg = document.createElement('img');
            canvasImg.src = renderedSrc;
            // Pass original image and multi-color rendered image on click to enable overlay mode
            canvasImg.onclick = () => openLightbox(originalSrc, renderedSrc);
            content = canvasImg;

            // Create legend
            if (categoryMap && Object.keys(categoryMap).length > 0) {
                const legendDiv = document.createElement('div');
                legendDiv.className = 'mask-legend';
                
                for (const [category, color] of Object.entries(categoryMap)) {
                    const item = document.createElement('div');
                    item.className = 'legend-item';
                    item.innerHTML = `
                        <div class="legend-color-box" style="background-color: ${color}"></div>
                        <span>${category}</span>
                    `;
                    legendDiv.appendChild(item);
                }
                // Insert legend after content and before span
                div.appendChild(content);
                div.appendChild(legendDiv);
                // Note: content has been appended, and will be appended again below, so be careful
                // For simplicity, I will remove or conditionally execute the following div.appendChild(content)
                content = null; // Mark as processed
            }
        } else {
            // Normal rendering mode
            const imageTag = document.createElement('img');
            imageTag.src = src;
            imageTag.onclick = () => openLightbox(src);
            content = imageTag;
        }
        
        const span = document.createElement('span');
        span.innerText = `${label}: ${img.file_name}`;
        
        if (content) {
            div.appendChild(content);
        }
        div.appendChild(span);
        container.appendChild(div);
    }
}
