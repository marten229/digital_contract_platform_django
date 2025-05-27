// PDF.js initialisieren
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

// Elemente holen
const pdfViewer = document.getElementById('pdfViewer');
const overlayCanvas = document.getElementById('overlayCanvas');
const selectAreaBtn = document.getElementById('selectSignatureArea');
const selectionHint = document.getElementById('selectionHint');
const currentSignatureTypeText = document.getElementById('currentSignatureTypeText');
const prevPageBtn = document.getElementById('prevPage');
const nextPageBtn = document.getElementById('nextPage');
const currentPageNumSpan = document.getElementById('currentPageNum');
const totalPagesSpan = document.getElementById('totalPages');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingMessage = document.getElementById('loadingMessage');
const workflowSteps = document.querySelectorAll('.workflow-step');
const pdfContainer = document.getElementById('pdfContainer');
const finishConfigurationBtn = document.getElementById('finishConfigurationBtn');

// Signature type radio buttons
const creatorSignatureRadio = document.getElementById('creatorSignature');
const partnerSignatureRadio = document.getElementById('partnerSignature');

// Signature status elements
const creatorSignatureStatus = document.getElementById('creatorSignatureStatus');
const partnerSignatureStatus = document.getElementById('partnerSignatureStatus');
const resetCreatorSignature = document.getElementById('resetCreatorSignature');
const resetPartnerSignature = document.getElementById('resetPartnerSignature');

// Hidden form inputs for signature positions
const creatorSignatureXInput = document.getElementById('creatorSignatureX');
const creatorSignatureYInput = document.getElementById('creatorSignatureY');
const creatorSignatureWidthInput = document.getElementById('creatorSignatureWidth');
const creatorSignatureHeightInput = document.getElementById('creatorSignatureHeight');
const creatorSignaturePageInput = document.getElementById('creatorSignaturePage');

const partnerSignatureXInput = document.getElementById('partnerSignatureX');
const partnerSignatureYInput = document.getElementById('partnerSignatureY');
const partnerSignatureWidthInput = document.getElementById('partnerSignatureWidth');
const partnerSignatureHeightInput = document.getElementById('partnerSignatureHeight');
const partnerSignaturePageInput = document.getElementById('partnerSignaturePage');

// Context für Overlay Canvas
const ctx = overlayCanvas.getContext('2d');

// Application state
let selectionMode = false;
let currentSignatureType = 'creator'; // 'creator' or 'partner'
let creatorSignature = null;
let partnerSignature = null;

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

// PDF laden und anzeigen
let pdfDoc = null;
let currentPage = 1;
let pageRendering = false;
let currentViewport = null;  // Store the current viewport
let actualPdfWidth = 0;      // Actual PDF width
let actualPdfHeight = 0;     // Actual PDF height
let pageNumPending = null;

// Update the renderPage function to properly handle page changes
const renderPage = (pageNum) => {
    pageRendering = true;
    showLoading('Seite wird geladen...');
    
    // Update the displayed page number
    currentPageNumSpan.textContent = pageNum;
    
    // Clear any existing signature rectangles
    clearOverlay();
    
    // Get the page
    pdfDoc.getPage(pageNum).then(page => {
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
              // Explizit Canvas-Position und -Größe setzen
            overlayCanvas.style.position = 'absolute';
            overlayCanvas.style.top = '0px';
            overlayCanvas.style.left = '0px';
            overlayCanvas.style.zIndex = '10';
            overlayCanvas.style.pointerEvents = 'auto';
            
            // Redraw signatures if they exist on this page
            redrawSignatures(pageNum);
            
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
function loadPdf(pdfUrl) {
    // Show loading before PDF load starts
    showLoading('PDF wird geladen...');
    
    // PDF laden with better error handling
    pdfjsLib.getDocument(pdfUrl).promise
        .then(doc => {
            pdfDoc = doc;
            totalPagesSpan.textContent = doc.numPages;
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
    
    return {
        x: pdfX,
        y: pdfY,
        width: pdfWidth,
        height: pdfHeight
    };
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

// Signature type toggle
creatorSignatureRadio.addEventListener('change', function() {
    if (this.checked) {
        currentSignatureType = 'creator';
        currentSignatureTypeText.textContent = 'Ihre';
    }
});

partnerSignatureRadio.addEventListener('change', function() {
    if (this.checked) {
        currentSignatureType = 'partner';
        currentSignatureTypeText.textContent = 'Partner';
    }
});

// Reset signature buttons
resetCreatorSignature.addEventListener('click', function() {
    creatorSignature = null;
    creatorSignatureStatus.textContent = 'Noch nicht festgelegt';
    resetCreatorSignature.classList.add('d-none');
    
    // Clear hidden inputs
    creatorSignatureXInput.value = '';
    creatorSignatureYInput.value = '';
    creatorSignatureWidthInput.value = '';
    creatorSignatureHeightInput.value = '';
    creatorSignaturePageInput.value = '';
    
    // Redraw to remove the signature
    redrawSignatures(currentPage);
    
    // Check if finish button should be enabled
    updateFinishButtonState();
});

resetPartnerSignature.addEventListener('click', function() {
    partnerSignature = null;
    partnerSignatureStatus.textContent = 'Noch nicht festgelegt';
    resetPartnerSignature.classList.add('d-none');
    
    // Clear hidden inputs
    partnerSignatureXInput.value = '';
    partnerSignatureYInput.value = '';
    partnerSignatureWidthInput.value = '';
    partnerSignatureHeightInput.value = '';
    partnerSignaturePageInput.value = '';
    
    // Redraw to remove the signature
    redrawSignatures(currentPage);
    
    // Check if finish button should be enabled
    updateFinishButtonState();
});

// Variablen für die Rechteck-Auswahl
let isDrawing = false;
let startX, startY;
let endX, endY;

// Aktiviere Rechteck-Zeichnen
selectAreaBtn.addEventListener('click', function() {
    selectionMode = true;
    updateWorkflowStep(2);
    
    // Reset drawing variables
    isDrawing = false;
    startX = undefined;
    startY = undefined;
    endX = undefined;
    endY = undefined;
    
    // Show selection instructions
    selectionHint.classList.remove('d-none');
    
    // Canvas konfigurieren
    overlayCanvas.style.position = 'absolute';
    overlayCanvas.style.top = '0px';
    overlayCanvas.style.left = '0px';
    overlayCanvas.style.zIndex = '999';
    overlayCanvas.style.cursor = 'crosshair';
    overlayCanvas.style.pointerEvents = 'auto';
    
    clearOverlay();
    
    // Redraw existing signatures after clearing
    redrawSignatures(currentPage);
});

// Overlay Canvas löschen
function clearOverlay() {
    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
}

// Rechteck zeichnen während der Auswahl
function drawSelectionRect() {
    const width = endX - startX;
    const height = endY - startY;
    
    ctx.strokeStyle = '#2196F3';
    ctx.lineWidth = 2;
    ctx.strokeRect(startX, startY, width, height);
    
    // Add semi-transparent fill
    ctx.fillStyle = 'rgba(33, 150, 243, 0.1)';
    ctx.fillRect(startX, startY, width, height);
}

// Draw a signature rectangle on the overlay canvas
function drawSignatureRect(rect, isCreator) {
    if (!rect) return;
    
    // Skip if the rectangle is not on the current page
    if (rect.page !== currentPage) return;
    
    // Use different colors for creator vs partner
    const color = isCreator ? '#28a745' : '#dc3545';
    
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
    
    // Add semi-transparent fill
    ctx.fillStyle = isCreator ? 'rgba(40, 167, 69, 0.1)' : 'rgba(220, 53, 69, 0.1)';
    ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
    
    // Add label
    ctx.fillStyle = color;
    ctx.font = '12px Arial';
    const label = isCreator ? 'Ihre Unterschrift' : 'Partner Unterschrift';
    ctx.fillText(label, rect.x, rect.y - 5);
}

// Redraw all signature rectangles
function redrawSignatures(pageNum) {
    clearOverlay();
    
    // Draw creator signature if it exists and is on this page
    if (creatorSignature && creatorSignature.page === pageNum) {
        drawSignatureRect(creatorSignature, true);
    }
    
    // Draw partner signature if it exists and is on this page
    if (partnerSignature && partnerSignature.page === pageNum) {
        drawSignatureRect(partnerSignature, false);
    }
}

// Get the modal elements
const creatorSigningModal = document.getElementById('creatorSigningModal');
const skipSigningBtn = document.getElementById('skipSigningBtn');
const signNowBtn = document.getElementById('signNowBtn');
const configurationForm = document.getElementById('configurationForm');

// Update the finish button state based on signatures
function updateFinishButtonState() {
    // Enable only if both signatures are defined
    if (creatorSignature && partnerSignature) {
        finishConfigurationBtn.disabled = false;
        updateWorkflowStep(3);
        
        // Show the creator signing option if it exists
        const creatorSigningOption = document.getElementById('creatorSigningOption');
        if (creatorSigningOption) {
            creatorSigningOption.classList.remove('d-none');
        }
    } else {
        finishConfigurationBtn.disabled = true;
        
        // Hide the creator signing option if it exists
        const creatorSigningOption = document.getElementById('creatorSigningOption');
        if (creatorSigningOption) {
            creatorSigningOption.classList.add('d-none');
        }
    }
}

// Set up event listener for the finish configuration button
finishConfigurationBtn.addEventListener('click', function(e) {
    // Prevent default form submission
    e.preventDefault();
    
    // Show the modal asking if the creator wants to sign
    const modal = new bootstrap.Modal(creatorSigningModal);
    modal.show();
});

// Set up the skip signing button to submit the form (only once)
skipSigningBtn.addEventListener('click', function() {
    // Hide the modal first
    const modal = bootstrap.Modal.getInstance(creatorSigningModal);
    if (modal) {
        modal.hide();
    }
    
    // Submit the form without redirect flag
    configurationForm.submit();
});

// Set up the sign now button to submit the form and redirect (only once)
signNowBtn.addEventListener('click', function() {
    // Hide the modal first
    const modal = bootstrap.Modal.getInstance(creatorSigningModal);
    if (modal) {
        modal.hide();
    }
    
    // Add a hidden field to indicate redirect to signing page
    let redirectInput = document.getElementById('redirectToSigning');
    if (!redirectInput) {
        redirectInput = document.createElement('input');
        redirectInput.type = 'hidden';
        redirectInput.name = 'redirect_to_signing';
        redirectInput.id = 'redirectToSigning';
        redirectInput.value = 'true';
        configurationForm.appendChild(redirectInput);
    } else {
        redirectInput.value = 'true';
    }
    
    // Submit the form
    configurationForm.submit();
});

// Add touch event handlers as fallback for signature area selection
overlayCanvas.addEventListener('touchstart', function(e) {
    if (!selectionMode) {
        return;
    }
    
    // Prevent all default behaviors
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    
    const rect = overlayCanvas.getBoundingClientRect();
    const touch = e.touches[0];
    startX = touch.clientX - rect.left;
    startY = touch.clientY - rect.top;
    isDrawing = true;
    
    // Clear the overlay but keep existing signatures
    clearOverlay();
    redrawSignatures(currentPage);
}, { passive: false });

overlayCanvas.addEventListener('touchmove', function(e) {
    if (!selectionMode || !isDrawing) {
        return;
    }
    
    // Prevent all default behaviors
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    
    const rect = overlayCanvas.getBoundingClientRect();
    const touch = e.touches[0];
    endX = touch.clientX - rect.left;
    endY = touch.clientY - rect.top;
    
    // Redraw existing signatures and the selection rectangle
    clearOverlay();
    redrawSignatures(currentPage);
    drawSelectionRect();
}, { passive: false });

overlayCanvas.addEventListener('touchend', function(e) {
    if (!selectionMode || !isDrawing) {
        return;
    }
    
    // Prevent all default behaviors
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    
    isDrawing = false;
    
    // Normalize rectangle (ensure width and height are positive)    const x = Math.min(startX, endX);
    const y = Math.min(startY, endY);
    const width = Math.abs(endX - startX);
    const height = Math.abs(endY - startY);
    
    // Only save if the size is reasonable
    if (width > 20 && height > 20) {
        // Convert coordinates to PDF space
        const pdfCoords = canvasToPdfCoordinates(x, y, width, height);
        
        // Save the signature rectangle based on current type
        if (currentSignatureType === 'creator') {
            creatorSignature = { x, y, width, height, page: currentPage };
            creatorSignatureStatus.textContent = `Festgelegt auf Seite ${currentPage}`;
            resetCreatorSignature.classList.remove('d-none');
            
            // Set form input values for creator signature
            creatorSignatureXInput.value = pdfCoords.x;
            creatorSignatureYInput.value = pdfCoords.y;
            creatorSignatureWidthInput.value = pdfCoords.width;
            creatorSignatureHeightInput.value = pdfCoords.height;
            creatorSignaturePageInput.value = currentPage;
        } else {
            partnerSignature = { x, y, width, height, page: currentPage };
            partnerSignatureStatus.textContent = `Festgelegt auf Seite ${currentPage}`;
            resetPartnerSignature.classList.remove('d-none');
            
            // Set form input values for partner signature
            partnerSignatureXInput.value = pdfCoords.x;
            partnerSignatureYInput.value = pdfCoords.y;
            partnerSignatureWidthInput.value = pdfCoords.width;
            partnerSignatureHeightInput.value = pdfCoords.height;
            partnerSignaturePageInput.value = currentPage;
        }
          // Exit selection mode
        selectionMode = false;
        overlayCanvas.style.cursor = 'default';
        selectionHint.classList.add('d-none');
        
        // Check if we can enable the finish button
        updateFinishButtonState();
    } else {
        alert('Bitte wählen Sie einen größeren Bereich für die Unterschrift aus.');
        
        // Clear overlay and redraw existing signatures
        clearOverlay();
        redrawSignatures(currentPage);
    }
}, { passive: false });

// Initialize function to set up everything
function initContractConfiguration(pdfUrl, csrfToken) {
    // Load PDF
    loadPdf(pdfUrl);
    
    // Initialize by showing step 1 as active
    updateWorkflowStep(1);
    
    // Make sure pdfContainer has position relative for overlay canvas
    if (pdfContainer && window.getComputedStyle(pdfContainer).position !== 'relative') {
        pdfContainer.style.position = 'relative';
    }
      // Ensure canvas element exists before attaching event listeners
    if (!overlayCanvas) {
        console.error('Overlay canvas not found!');
        return;
    }
    
    // Event listeners for signature area selection
    overlayCanvas.addEventListener('mousedown', function(e) {
        if (!selectionMode) return;
        
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        
        const rect = overlayCanvas.getBoundingClientRect();
        startX = e.clientX - rect.left;
        startY = e.clientY - rect.top;
        isDrawing = true;
        
        clearOverlay();
        redrawSignatures(currentPage);
    }, true);

    overlayCanvas.addEventListener('mousemove', function(e) {
        if (!selectionMode || !isDrawing) return;
        
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        
        const rect = overlayCanvas.getBoundingClientRect();
        endX = e.clientX - rect.left;
        endY = e.clientY - rect.top;
        
        clearOverlay();
        redrawSignatures(currentPage);
        drawSelectionRect();
    }, true);

    overlayCanvas.addEventListener('mouseup', function(e) {
        if (!selectionMode || !isDrawing) return;
        
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        
        isDrawing = false;
        
        const x = Math.min(startX, endX);
        const y = Math.min(startY, endY);
        const width = Math.abs(endX - startX);
        const height = Math.abs(endY - startY);
        
        if (width > 20 && height > 20) {
            const pdfCoords = canvasToPdfCoordinates(x, y, width, height);            
            if (currentSignatureType === 'creator') {
                creatorSignature = { x, y, width, height, page: currentPage };
                creatorSignatureStatus.textContent = `Festgelegt auf Seite ${currentPage}`;
                resetCreatorSignature.classList.remove('d-none');
                
                creatorSignatureXInput.value = pdfCoords.x;
                creatorSignatureYInput.value = pdfCoords.y;
                creatorSignatureWidthInput.value = pdfCoords.width;
                creatorSignatureHeightInput.value = pdfCoords.height;
                creatorSignaturePageInput.value = currentPage;
            } else {
                partnerSignature = { x, y, width, height, page: currentPage };
                partnerSignatureStatus.textContent = `Festgelegt auf Seite ${currentPage}`;
                resetPartnerSignature.classList.remove('d-none');
                
                partnerSignatureXInput.value = pdfCoords.x;
                partnerSignatureYInput.value = pdfCoords.y;
                partnerSignatureWidthInput.value = pdfCoords.width;
                partnerSignatureHeightInput.value = pdfCoords.height;
                partnerSignaturePageInput.value = currentPage;
            }
            
            selectionMode = false;
            overlayCanvas.style.cursor = 'default';
            selectionHint.classList.add('d-none');
            
            updateFinishButtonState();
        } else {
            alert('Bitte wählen Sie einen größeren Bereich für die Unterschrift aus.');
            clearOverlay();
            redrawSignatures(currentPage);
        }
    }, true);

    // Document-level event delegation as backup
    document.addEventListener('mousedown', function(e) {
        if (e.target === overlayCanvas && selectionMode) {
            e.preventDefault();
            e.stopPropagation();
            
            const rect = overlayCanvas.getBoundingClientRect();
            startX = e.clientX - rect.left;
            startY = e.clientY - rect.top;
            isDrawing = true;
            
            clearOverlay();
            redrawSignatures(currentPage);
        }
    });
    
    document.addEventListener('mousemove', function(e) {
        if (isDrawing && selectionMode) {
            e.preventDefault();
            
            const rect = overlayCanvas.getBoundingClientRect();
            endX = e.clientX - rect.left;
            endY = e.clientY - rect.top;
            
            clearOverlay();
            redrawSignatures(currentPage);
            drawSelectionRect();
        }
    });
    
    document.addEventListener('mouseup', function(e) {
        if (isDrawing && selectionMode) {
            e.preventDefault();
            
            isDrawing = false;
            
            const x = Math.min(startX, endX);
            const y = Math.min(startY, endY);
            const width = Math.abs(endX - startX);
            const height = Math.abs(endY - startY);
            
            if (width > 20 && height > 20) {
                const pdfCoords = canvasToPdfCoordinates(x, y, width, height);
                
                if (currentSignatureType === 'creator') {
                    creatorSignature = { x, y, width, height, page: currentPage };
                    creatorSignatureStatus.textContent = `Festgelegt auf Seite ${currentPage}`;
                    resetCreatorSignature.classList.remove('d-none');
                    
                    creatorSignatureXInput.value = pdfCoords.x;
                    creatorSignatureYInput.value = pdfCoords.y;
                    creatorSignatureWidthInput.value = pdfCoords.width;
                    creatorSignatureHeightInput.value = pdfCoords.height;
                    creatorSignaturePageInput.value = currentPage;
                } else {
                    partnerSignature = { x, y, width, height, page: currentPage };
                    partnerSignatureStatus.textContent = `Festgelegt auf Seite ${currentPage}`;
                    resetPartnerSignature.classList.remove('d-none');
                    
                    partnerSignatureXInput.value = pdfCoords.x;
                    partnerSignatureYInput.value = pdfCoords.y;
                    partnerSignatureWidthInput.value = pdfCoords.width;
                    partnerSignatureHeightInput.value = pdfCoords.height;
                    partnerSignaturePageInput.value = currentPage;
                }
                
                selectionMode = false;
                overlayCanvas.style.cursor = 'default';
                selectionHint.classList.add('d-none');
                
                updateFinishButtonState();
            } else {
                alert('Bitte wählen Sie einen größeren Bereich für die Unterschrift aus.');
                clearOverlay();
                redrawSignatures(currentPage);
            }
        }
    });
}