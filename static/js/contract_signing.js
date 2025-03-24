// PDF.js initialisieren
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

// Elemente holen
const pdfViewer = document.getElementById('pdfViewer');
const overlayCanvas = document.getElementById('overlayCanvas');
const selectAreaBtn = document.getElementById('selectSignatureArea');
const selectionHint = document.getElementById('selectionHint');
const signatureContainer = document.getElementById('signatureContainer');
const clearBtn = document.getElementById('clearSignature');
const previewBtn = document.getElementById('previewSignature');
const cancelBtn = document.getElementById('cancelSignature');
const previewControls = document.getElementById('previewControls');
const confirmBtn = document.getElementById('confirmSignature');
const editBtn = document.getElementById('editSignature');
const cancelPreviewBtn = document.getElementById('cancelPreview');
const signatureCanvas = document.getElementById('signaturePad');
const prevPageBtn = document.getElementById('prevPage');
const nextPageBtn = document.getElementById('nextPage');
const currentPageNumSpan = document.getElementById('currentPageNum');
const totalPagesSpan = document.getElementById('totalPages');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingMessage = document.getElementById('loadingMessage');
const workflowSteps = document.querySelectorAll('.workflow-step');
const pdfContainer = document.getElementById('pdfContainer');

// Context für Overlay Canvas
const ctx = overlayCanvas.getContext('2d');

// Function to update workflow steps UI
function updateWorkflowStep(step) {
    workflowSteps.forEach((el, index) => {
        if (index + 1 === step) {
            el.classList.add('active');
        } else {
            el.classList.remove('active');
        }
    });
}

// Show loading overlay
function showLoading(message) {
    loadingMessage.textContent = message || 'Wird geladen...';
    loadingOverlay.style.display = 'flex';
}

// Hide loading overlay
function hideLoading() {
    loadingOverlay.style.display = 'none';
}

// Signature Pad initialisieren
const signaturePad = new SignaturePad(signatureCanvas, {
    backgroundColor: 'rgb(255, 255, 255)',
    penColor: 'rgb(0, 0, 0)'
});

// Make signature pad responsive
function resizeSignaturePad() {
    const container = document.getElementById('signatureContainer');
    const canvas = document.getElementById('signaturePad');
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    canvas.width = canvas.offsetWidth * ratio;
    canvas.height = canvas.offsetHeight * ratio;
    canvas.getContext("2d").scale(ratio, ratio);
    signaturePad.clear(); // Clear and re-render
}

window.addEventListener('resize', resizeSignaturePad);

// Application state
let selectionMode = false;
let previewMode = false;
let signatureDataURL = null;

// PDF laden und anzeigen
let pdfDoc = null;
let currentPage = 1;
let pageRendering = false;
let currentViewport = null;  // Store the current viewport
let actualPdfWidth = 0;      // Actual PDF width
let actualPdfHeight = 0;     // Actual PDF height
let pageNumPending = null;
let configuredSignatureRect = null; // Store the configured signature position

// Update the renderPage function to properly handle page changes
const renderPage = (pageNum) => {
    pageRendering = true;
    showLoading('Seite wird geladen...');
    
    // Update the displayed page number
    currentPageNumSpan.textContent = pageNum;
    
    // Clear any existing selection rectangle
    clearOverlay();
    
    console.log(`Rendering page ${pageNum}`);
    
    // Get the page
    pdfDoc.getPage(pageNum).then(page => {
        console.log(`Got page ${pageNum}, rendering`);
        
        // Get actual PDF dimensions at scale 1.0
        const originalViewport = page.getViewport({ scale: 1.0 });
        actualPdfWidth = originalViewport.width;
        actualPdfHeight = originalViewport.height;
        
        // Calculate scale to fit content within container width
        const containerWidth = pdfContainer.clientWidth;
        const scale = containerWidth / originalViewport.width;
        
        // Display viewport at calculated scale
        const viewport = page.getViewport({ scale: scale });
        currentViewport = viewport;  // Save viewport for coordinate conversion
        
        pdfViewer.width = viewport.width;
        pdfViewer.height = viewport.height;
        overlayCanvas.width = viewport.width;
        overlayCanvas.height = viewport.height;
        
        const renderContext = {
            canvasContext: pdfViewer.getContext('2d'),
            viewport: viewport
        };
        
        // Clear canvas before rendering new page
        pdfViewer.getContext('2d').clearRect(0, 0, pdfViewer.width, pdfViewer.height);
        
        page.render(renderContext).promise.then(() => {
            pageRendering = false;
            hideLoading();
            
            // Show "Select Signature" button if this is the page with the configured signature area
            if (configuredSignatureRect && configuredSignatureRect.page === pageNum) {
                selectAreaBtn.style.display = 'block';
                
                // Draw the configured signature area
                drawConfiguredSignatureArea();
            } else {
                selectAreaBtn.style.display = 'none';
            }
            
            // Redraw signature preview if in preview mode
            if (previewMode && signatureRect && signatureDataURL) {
                drawSignaturePreview();
            }
            
            // If there's a page pending to be rendered, do it now
            if (pageNumPending !== null) {
                renderPage(pageNumPending);
                pageNumPending = null;
            }
        }).catch(error => {
            console.error('Error rendering page:', error);
            pageRendering = false;
            hideLoading();
            alert('Fehler beim Rendern der Seite. Bitte versuchen Sie es erneut.');
        });
    }).catch(error => {
        console.error(`Error getting page ${pageNum}:`, error);
        pageRendering = false;
        hideLoading();
        alert('Fehler beim Laden der Seite. Bitte versuchen Sie es erneut.');
    });
};

// Function to queue a page render
const queueRenderPage = (pageNum) => {
    if (pageRendering) {
        pageNumPending = pageNum;
    } else {
        renderPage(pageNum);
    }
};

// Function to load PDF
function loadPdf(pdfUrl, signatureX, signatureY, signatureWidth, signatureHeight, signaturePage) {
    // Store the configured signature rectangle (in PDF coordinates)
    configuredSignatureRect = {
        x: signatureX,
        y: signatureY,
        width: signatureWidth, 
        height: signatureHeight,
        page: signaturePage
    };
    
    // Show loading before PDF load starts
    showLoading('PDF wird geladen...');
    
    // PDF laden with better error handling
    pdfjsLib.getDocument(pdfUrl).promise
        .then(doc => {
            console.log(`PDF loaded with ${doc.numPages} pages`);
            pdfDoc = doc;
            totalPagesSpan.textContent = doc.numPages;
            
            // If we have a configured signature page, start on that page
            if (configuredSignatureRect && configuredSignatureRect.page) {
                currentPage = configuredSignatureRect.page;
            }
            
            renderPage(currentPage);
            
            // Enable/disable page navigation buttons based on page count
            prevPageBtn.disabled = (currentPage <= 1);
            nextPageBtn.disabled = (currentPage >= doc.numPages);
        })
        .catch(error => {
            console.error('PDF laden fehlgeschlagen:', error);
            hideLoading();
            alert('Dokument konnte nicht geladen werden. Bitte versuchen Sie es später erneut.');
        });
}

// Function to convert PDF coordinates to canvas coordinates
function pdfToCanvasCoordinates(pdfX, pdfY, pdfWidth, pdfHeight) {
    if (!currentViewport) return { x: pdfX, y: pdfY, width: pdfWidth, height: pdfHeight };
    
    // Calculate scale factor between actual PDF and display
    const scaleX = currentViewport.width / actualPdfWidth;
    const scaleY = currentViewport.height / actualPdfHeight;
    
    // Convert from PDF coordinates (origin at bottom-left) to canvas coordinates (origin at top-left)
    const x = pdfX * scaleX;
    const y = currentViewport.height - (pdfY + pdfHeight) * scaleY;
    const width = pdfWidth * scaleX;
    const height = pdfHeight * scaleY;
    
    return { x, y, width, height };
}

// Function to convert canvas coordinates to PDF coordinates
function canvasToPdfCoordinates(x, y, width, height) {
    if (!currentViewport) return { x, y, width, height };
    
    // Calculate scale factor between display and actual PDF
    const scaleX = actualPdfWidth / currentViewport.width;
    const scaleY = actualPdfHeight / currentViewport.height;
    
    // Convert to PDF coordinates (origin at bottom-left)
    // 1. Scale to actual PDF dimensions
    // 2. Flip Y-coordinate (PDF origin is bottom-left)
    const pdfX = x * scaleX;
    const pdfY = actualPdfHeight - (y + height) * scaleY;
    const pdfWidth = width * scaleX;
    const pdfHeight = height * scaleY;
    
    console.log('Canvas coords:', {x, y, width, height});
    console.log('PDF coords:', {x: pdfX, y: pdfY, width: pdfWidth, height: pdfHeight});
    
    return {
        x: pdfX,
        y: pdfY,
        width: pdfWidth,
        height: pdfHeight
    };
}

// Draw the configured signature area on the canvas
function drawConfiguredSignatureArea() {
    if (!configuredSignatureRect || configuredSignatureRect.page !== currentPage) return;
    
    // Convert PDF coordinates to canvas coordinates
    const canvasCoords = pdfToCanvasCoordinates(
        configuredSignatureRect.x,
        configuredSignatureRect.y,
        configuredSignatureRect.width,
        configuredSignatureRect.height
    );
    
    // Draw a rectangle around the signature area
    ctx.strokeStyle = '#2196F3';
    ctx.lineWidth = 2;
    ctx.strokeRect(canvasCoords.x, canvasCoords.y, canvasCoords.width, canvasCoords.height);
    
    // Add semi-transparent fill
    ctx.fillStyle = 'rgba(33, 150, 243, 0.1)';
    ctx.fillRect(canvasCoords.x, canvasCoords.y, canvasCoords.width, canvasCoords.height);
    
    // Add text label
    ctx.fillStyle = '#2196F3';
    ctx.font = '14px Arial';
    ctx.fillText('Hier unterschreiben', canvasCoords.x, canvasCoords.y - 5);
    
    // Store the canvas coordinates for later use
    signatureRect = canvasCoords;
}

// Previous page navigation
prevPageBtn.addEventListener('click', () => {
    if (currentPage <= 1) return;
    currentPage--;
    queueRenderPage(currentPage);
    
    // Update button states
    prevPageBtn.disabled = (currentPage <= 1);
    nextPageBtn.disabled = (currentPage >= pdfDoc.numPages);
});

// Next page navigation
nextPageBtn.addEventListener('click', () => {
    if (currentPage >= pdfDoc.numPages) return;
    currentPage++;
    queueRenderPage(currentPage);
    
    // Update button states
    prevPageBtn.disabled = (currentPage <= 1);
    nextPageBtn.disabled = (currentPage >= pdfDoc.numPages);
});

// Variablen für die Rechteck-Auswahl
let isDrawing = false;
let startX, startY;
let endX, endY;
let signatureRect = null;

// Aktiviere Signature-Pad
selectAreaBtn.addEventListener('click', function() {
    selectionMode = false; // No need for selection mode with preconfigured areas
    previewMode = false;
    updateWorkflowStep(2);
    
    // Show the signature container directly
    signatureContainer.style.display = 'block';
    
    // Hide selection instructions
    selectionHint.classList.add('d-none');
    
    // Make sure signature pad is properly sized
    resizeSignaturePad();
});

// Overlay Canvas löschen
function clearOverlay() {
    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
}

// Rechteck zeichnen
function drawRect() {
    clearOverlay();
    ctx.strokeStyle = '#2196F3';
    ctx.lineWidth = 2;
    const width = endX - startX;
    const height = endY - startY;
    ctx.strokeRect(startX, startY, width, height);
    
    // Add semi-transparent fill
    ctx.fillStyle = 'rgba(33, 150, 243, 0.1)';
    ctx.fillRect(startX, startY, width, height);
}

// Draw signature preview on overlay canvas
function drawSignaturePreview() {
    if (!signatureRect || !signatureDataURL) return;
    
    const img = new Image();
    img.onload = () => {
        // Draw rectangle
        ctx.strokeStyle = '#28a745';
        ctx.lineWidth = 2;
        ctx.strokeRect(signatureRect.x, signatureRect.y, signatureRect.width, signatureRect.height);
        
        // Draw signature
        ctx.drawImage(
            img, 
            signatureRect.x, 
            signatureRect.y, 
            signatureRect.width, 
            signatureRect.height
        );
    };
    img.src = signatureDataURL;
}

// Canvas leeren
clearBtn.addEventListener('click', function() {
    signaturePad.clear();
});

// Abbrechen (Selection)
cancelBtn.addEventListener('click', function() {
    signatureContainer.style.display = 'none';
    clearOverlay();
    selectionMode = false;
    overlayCanvas.style.cursor = 'default';
    
    // Draw the configured signature area again
    drawConfiguredSignatureArea();
    
    updateWorkflowStep(1);
});

// Preview signature
previewBtn.addEventListener('click', function() {
    if (signaturePad.isEmpty()) {
        alert("Bitte zuerst unterschreiben!");
        return;
    }
    
    // Get signature data URL and store it
    signatureDataURL = signaturePad.toDataURL();
    
    // Hide signature container and show preview controls
    signatureContainer.style.display = 'none';
    previewControls.style.display = 'block';
    
    // Set preview mode
    previewMode = true;
    selectionMode = false;
    updateWorkflowStep(3);
    
    // Draw signature preview
    drawSignaturePreview();
});

// Cancel preview
cancelPreviewBtn.addEventListener('click', function() {
    previewMode = false;
    previewControls.style.display = 'none';
    clearOverlay();
    overlayCanvas.style.cursor = 'default';
    
    // Draw the configured signature area again
    drawConfiguredSignatureArea();
    
    updateWorkflowStep(1);
});

// Edit signature - go back to signature pad
editBtn.addEventListener('click', function() {
    previewMode = false;
    previewControls.style.display = 'none';
    signatureContainer.style.display = 'block';
    clearOverlay();
    
    // Draw the configured signature area in the background
    drawConfiguredSignatureArea();
    
    updateWorkflowStep(2);
});

// Confirm and save signature
function saveSignature(url, csrfToken) {
    if (!signatureRect || !signatureDataURL) {
        alert("Fehler: Keine Unterschrift oder Position gefunden.");
        return;
    }
    
    showLoading('Unterschrift wird gespeichert...');
    
    // Convert canvas coordinates to PDF coordinates
    const pdfCoords = canvasToPdfCoordinates(
        signatureRect.x, 
        signatureRect.y, 
        signatureRect.width, 
        signatureRect.height
    );
    
    // Sende die Unterschrift und Koordinaten per POST an den Django-View
    fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": csrfToken
        },
        body: new URLSearchParams({
            'signature': signatureDataURL,
            'x': pdfCoords.x,
            'y': pdfCoords.y,
            'width': pdfCoords.width,
            'height': pdfCoords.height,
            'page': currentPage
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error("Fehler beim Hinzufügen der Unterschrift");
        }
        return response.blob();
    })
    .then(blob => {
        // Erstelle einen Downloadlink für die signierte PDF
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = 'signed_contract.pdf';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        
        // UI zurücksetzen
        previewMode = false;
        previewControls.style.display = 'none';
        clearOverlay();
        signatureRect = null;
        signatureDataURL = null;
        overlayCanvas.style.cursor = 'default';
        updateWorkflowStep(1);
        
        hideLoading();
        
        // Success message
        alert("Unterschrift erfolgreich hinzugefügt! Das signierte Dokument wurde heruntergeladen.");
    })
    .catch(error => {
        console.error("Fehler:", error);
        hideLoading();
        alert("Beim Speichern der Unterschrift ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut.");
    });
}

// Initialize function to set up everything
function initContractDetail(pdfUrl, signatureUrl, csrfToken, signatureX, signatureY, signatureWidth, signatureHeight, signaturePage, isCreator) {
    // Load PDF with the configured signature position
    loadPdf(pdfUrl, signatureX, signatureY, signatureWidth, signatureHeight, signaturePage);
    
    // Initialize by showing step 1 as active
    updateWorkflowStep(1);
    
    // Update UI text based on who is signing
    if (isCreator) {
        // Update any role-specific text
        const instructionsCard = document.querySelector('.card-title');
        if (instructionsCard) {
            instructionsCard.innerHTML = '<i class="bi bi-info-circle me-2"></i>Hinweise (Ersteller)';
        }
    }
    
    // Setup confirm button
    confirmBtn.addEventListener('click', function() {
        saveSignature(signatureUrl, csrfToken);
    });
}
