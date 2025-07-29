pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

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

const selectionPreview = document.getElementById('selectionPreview');
const signatureControls = document.getElementById('signatureControls');
const confirmSelectionBtn = document.getElementById('confirmSelection');
const cancelSelectionBtn = document.getElementById('cancelSelection');

const creatorSignatureRadio = document.getElementById('creatorSignature');
const partnerSignatureRadio = document.getElementById('partnerSignature');

const creatorSignatureStatus = document.getElementById('creatorSignatureStatus');
const partnerSignatureStatus = document.getElementById('partnerSignatureStatus');
const resetCreatorSignature = document.getElementById('resetCreatorSignature');
const resetPartnerSignature = document.getElementById('resetPartnerSignature');

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

const ctx = overlayCanvas.getContext('2d');

let selectionMode = false;
let currentSignatureType = 'creator';
let creatorSignature = null;
let partnerSignature = null;

let pendingSelection = null; 
let isSelectionConfirmed = false;

function showSelectionPreview(x, y, width, height) {
    selectionPreview.style.left = x + 'px';
    selectionPreview.style.top = y + 'px';
    selectionPreview.style.width = width + 'px';
    selectionPreview.style.height = height + 'px';
    selectionPreview.style.display = 'block';
    
    const canvasWidth = overlayCanvas.width;
    const controlsWidth = 70;
    
    let controlsX = x + width - controlsWidth;
    if (controlsX + controlsWidth > canvasWidth) {
        controlsX = canvasWidth - controlsWidth - 5;
    }
    if (controlsX < 5) {
        controlsX = 5; 
    }
    
    const controlsY = y - 35;
    
    signatureControls.style.left = controlsX + 'px';
    signatureControls.style.top = Math.max(5, controlsY) + 'px';
    signatureControls.style.display = 'flex';
}

function hideSelectionPreview() {
    selectionPreview.style.display = 'none';
    signatureControls.style.display = 'none';
    pendingSelection = null;
    isSelectionConfirmed = false;
}

function confirmSelection() {
    if (!pendingSelection) return;
    
    const { x, y, width, height } = pendingSelection;
    const pdfCoords = canvasToPdfCoordinates(x, y, width, height);
    
    let shouldContinueSelection = false;
    
    if (currentSignatureType === 'creator') {
        creatorSignature = { x, y, width, height, page: currentPage };
        creatorSignatureStatus.textContent = `Festgelegt auf Seite ${currentPage}`;
        resetCreatorSignature.classList.remove('d-none');
        
        creatorSignatureXInput.value = pdfCoords.x;
        creatorSignatureYInput.value = pdfCoords.y;
        creatorSignatureWidthInput.value = pdfCoords.width;
        creatorSignatureHeightInput.value = pdfCoords.height;
        creatorSignaturePageInput.value = currentPage;
        
        if (!partnerSignature) {
            partnerSignatureRadio.checked = true;
            currentSignatureType = 'partner';
            currentSignatureTypeText.textContent = 'Partner';
            shouldContinueSelection = true;
        }
    } else {
        partnerSignature = { x, y, width, height, page: currentPage };
        partnerSignatureStatus.textContent = `Festgelegt auf Seite ${currentPage}`;
        resetPartnerSignature.classList.remove('d-none');
        
        partnerSignatureXInput.value = pdfCoords.x;
        partnerSignatureYInput.value = pdfCoords.y;
        partnerSignatureWidthInput.value = pdfCoords.width;
        partnerSignatureHeightInput.value = pdfCoords.height;
        partnerSignaturePageInput.value = currentPage;
        
        if (!creatorSignature) {
            creatorSignatureRadio.checked = true;
            currentSignatureType = 'creator';
            currentSignatureTypeText.textContent = 'Ihre';
            shouldContinueSelection = true;
        }
    }
    
    hideSelectionPreview();
    
    redrawSignatures(currentPage);
    
    if (shouldContinueSelection) {
        selectionMode = true;
        selectionHint.classList.remove('d-none');
        overlayCanvas.style.cursor = 'crosshair';
        
        isDrawing = false;
        startX = undefined;
        startY = undefined;
        endX = undefined;
        endY = undefined;
    } else {
        exitSelectionMode();
    }
    
    updateFinishButtonState();
}

function cancelSelection() {
    hideSelectionPreview();
    clearOverlay();
    redrawSignatures(currentPage);
}

function exitSelectionMode() {
    selectionMode = false;
    overlayCanvas.style.cursor = 'default';
    selectionHint.classList.add('d-none');
    hideSelectionPreview();
}

function updateWorkflowStep(step) {
    workflowSteps.forEach((el, index) => {
        if (index + 1 === step) {
            el.classList.add('active');
        } else {
            el.classList.remove('active');
        }
    });
}

function showLoading(message) {
    loadingMessage.textContent = message || 'Wird geladen...';
    loadingOverlay.style.display = 'flex';
}

function hideLoading() {
    loadingOverlay.style.display = 'none';
}

let pdfDoc = null;
let currentPage = 1;
let pageRendering = false;
let currentViewport = null;
let actualPdfWidth = 0;
let actualPdfHeight = 0;
let pageNumPending = null;

const renderPage = (pageNum) => {
    pageRendering = true;
    showLoading('Seite wird geladen...');
    
    currentPageNumSpan.textContent = pageNum;

    clearOverlay();
    
    pdfDoc.getPage(pageNum).then(page => {
        const originalViewport = page.getViewport({ scale: 1.0 });
        actualPdfWidth = originalViewport.width;
        actualPdfHeight = originalViewport.height;
        
        const containerWidth = pdfContainer.clientWidth;
        const scale = containerWidth / originalViewport.width;
        
        const viewport = page.getViewport({ scale: scale });
        currentViewport = viewport;
        
        pdfViewer.width = viewport.width;
        pdfViewer.height = viewport.height;
        overlayCanvas.width = viewport.width;
        overlayCanvas.height = viewport.height;
        
        const renderContext = {
            canvasContext: pdfViewer.getContext('2d'),
            viewport: viewport
        };
        
        pdfViewer.getContext('2d').clearRect(0, 0, pdfViewer.width, pdfViewer.height);
          page.render(renderContext).promise.then(() => {
            pageRendering = false;
            hideLoading();
            overlayCanvas.style.position = 'absolute';
            overlayCanvas.style.top = '0px';
            overlayCanvas.style.left = '0px';
            overlayCanvas.style.zIndex = '10';
            overlayCanvas.style.pointerEvents = 'auto';
            
            redrawSignatures(pageNum);
            
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

const queueRenderPage = (pageNum) => {
    if (pageRendering) {
        pageNumPending = pageNum;
    } else {
        renderPage(pageNum);
    }
};

function loadPdf(pdfUrl) {
    showLoading('PDF wird geladen...');
    
    pdfjsLib.getDocument(pdfUrl).promise
        .then(doc => {
            pdfDoc = doc;
            totalPagesSpan.textContent = doc.numPages;
            renderPage(currentPage);
            
            prevPageBtn.disabled = (currentPage <= 1);
            nextPageBtn.disabled = (currentPage >= doc.numPages);
        })
        .catch(error => {
            console.error('PDF laden fehlgeschlagen:', error);
            hideLoading();
            alert('Dokument konnte nicht geladen werden. Bitte versuchen Sie es später erneut.');
        });
}

function canvasToPdfCoordinates(x, y, width, height) {
    if (!currentViewport) return { x, y, width, height };
    
    const scaleX = actualPdfWidth / currentViewport.width;
    const scaleY = actualPdfHeight / currentViewport.height;
    
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

function pdfToCanvasCoordinates(pdfX, pdfY, pdfWidth, pdfHeight) {
    if (!currentViewport) return { x: pdfX, y: pdfY, width: pdfWidth, height: pdfHeight };
    
    const scaleX = currentViewport.width / actualPdfWidth;
    const scaleY = currentViewport.height / actualPdfHeight;
    
    const x = pdfX * scaleX;
    const y = currentViewport.height - (pdfY + pdfHeight) * scaleY;
    const width = pdfWidth * scaleX;
    const height = pdfHeight * scaleY;
    
    return { x, y, width, height };
}

prevPageBtn.addEventListener('click', () => {
    if (currentPage <= 1) return;
    
    hideSelectionPreview();
    
    currentPage--;
    queueRenderPage(currentPage);
    
    prevPageBtn.disabled = (currentPage <= 1);
    nextPageBtn.disabled = (currentPage >= pdfDoc.numPages);
});

nextPageBtn.addEventListener('click', () => {
    if (currentPage >= pdfDoc.numPages) return;
    
    hideSelectionPreview();
    
    currentPage++;
    queueRenderPage(currentPage);
    
    prevPageBtn.disabled = (currentPage <= 1);
    nextPageBtn.disabled = (currentPage >= pdfDoc.numPages);
});

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

resetCreatorSignature.addEventListener('click', function() {
    creatorSignature = null;
    creatorSignatureStatus.textContent = 'Noch nicht festgelegt';
    resetCreatorSignature.classList.add('d-none');
    
    creatorSignatureXInput.value = '';
    creatorSignatureYInput.value = '';
    creatorSignatureWidthInput.value = '';
    creatorSignatureHeightInput.value = '';
    creatorSignaturePageInput.value = '';
    
    redrawSignatures(currentPage);
    
    updateFinishButtonState();
});

resetPartnerSignature.addEventListener('click', function() {
    partnerSignature = null;
    partnerSignatureStatus.textContent = 'Noch nicht festgelegt';
    resetPartnerSignature.classList.add('d-none');
    
    partnerSignatureXInput.value = '';
    partnerSignatureYInput.value = '';
    partnerSignatureWidthInput.value = '';
    partnerSignatureHeightInput.value = '';
    partnerSignaturePageInput.value = '';
    
    redrawSignatures(currentPage);
    
    updateFinishButtonState();
});

confirmSelectionBtn.addEventListener('click', confirmSelection);
cancelSelectionBtn.addEventListener('click', cancelSelection);

let isDrawing = false;
let startX, startY;
let endX, endY;

selectAreaBtn.addEventListener('click', function() {
    selectionMode = true;
    updateWorkflowStep(2);
    
    hideSelectionPreview();
    
    isDrawing = false;
    startX = undefined;
    startY = undefined;
    endX = undefined;
    endY = undefined;
    
    selectionHint.classList.remove('d-none');
    
    overlayCanvas.style.position = 'absolute';
    overlayCanvas.style.top = '0px';
    overlayCanvas.style.left = '0px';
    overlayCanvas.style.zIndex = '999';
    overlayCanvas.style.cursor = 'crosshair';
    overlayCanvas.style.pointerEvents = 'auto';
    
    clearOverlay();
    
    redrawSignatures(currentPage);
});

function clearOverlay() {
    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
}

function drawSelectionRect() {
    const width = endX - startX;
    const height = endY - startY;
    
    ctx.strokeStyle = '#2196F3';
    ctx.lineWidth = 2;
    ctx.strokeRect(startX, startY, width, height);
    
    ctx.fillStyle = 'rgba(33, 150, 243, 0.1)';
    ctx.fillRect(startX, startY, width, height);
}

function drawSignatureRect(rect, isCreator) {
    if (!rect) return;
    
    if (rect.page !== currentPage) return;
    
    const color = isCreator ? '#28a745' : '#dc3545';
    
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
    
    ctx.fillStyle = isCreator ? 'rgba(40, 167, 69, 0.1)' : 'rgba(220, 53, 69, 0.1)';
    ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
    
    ctx.fillStyle = color;
    ctx.font = '12px Arial';
    const label = isCreator ? 'Ihre Unterschrift' : 'Partner Unterschrift';
    ctx.fillText(label, rect.x, rect.y - 5);
}

function redrawSignatures(pageNum) {
    clearOverlay();
    
    if (creatorSignature && creatorSignature.page === pageNum) {
        drawSignatureRect(creatorSignature, true);
    }
    
    if (partnerSignature && partnerSignature.page === pageNum) {
        drawSignatureRect(partnerSignature, false);
    }
}

const creatorSigningModal = document.getElementById('creatorSigningModal');
const skipSigningBtn = document.getElementById('skipSigningBtn');
const signNowBtn = document.getElementById('signNowBtn');
const configurationForm = document.getElementById('configurationForm');

function updateFinishButtonState() {
    if (creatorSignature && partnerSignature) {
        finishConfigurationBtn.disabled = false;
        updateWorkflowStep(3);
        
        const creatorSigningOption = document.getElementById('creatorSigningOption');
        if (creatorSigningOption) {
            creatorSigningOption.classList.remove('d-none');
        }
    } else {
        finishConfigurationBtn.disabled = true;
        
        const creatorSigningOption = document.getElementById('creatorSigningOption');
        if (creatorSigningOption) {
            creatorSigningOption.classList.add('d-none');
        }
    }
}

finishConfigurationBtn.addEventListener('click', function(e) {
    e.preventDefault();
    
    const modal = new bootstrap.Modal(creatorSigningModal);
    modal.show();
});

skipSigningBtn.addEventListener('click', function() {
    const modal = bootstrap.Modal.getInstance(creatorSigningModal);
    if (modal) {
        modal.hide();
    }
    
    configurationForm.submit();
});

signNowBtn.addEventListener('click', function() {
    const modal = bootstrap.Modal.getInstance(creatorSigningModal);
    if (modal) {
        modal.hide();
    }
    
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
    
    configurationForm.submit();
});

overlayCanvas.addEventListener('touchstart', function(e) {
    if (!selectionMode) {
        return;
    }
    
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    
    const rect = overlayCanvas.getBoundingClientRect();
    const touch = e.touches[0];
    startX = touch.clientX - rect.left;
    startY = touch.clientY - rect.top;
    isDrawing = true;
    
    hideSelectionPreview();
    
    clearOverlay();
    redrawSignatures(currentPage);
}, { passive: false });

overlayCanvas.addEventListener('touchmove', function(e) {
    if (!selectionMode || !isDrawing) {
        return;
    }
    
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    
    const rect = overlayCanvas.getBoundingClientRect();
    const touch = e.touches[0];
    endX = touch.clientX - rect.left;
    endY = touch.clientY - rect.top;
    
    clearOverlay();
    redrawSignatures(currentPage);
    drawSelectionRect();
}, { passive: false });

overlayCanvas.addEventListener('touchend', function(e) {
    if (!selectionMode || !isDrawing) {
        return;
    }
    
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    
    isDrawing = false;
    
    const x = Math.min(startX, endX);
    const y = Math.min(startY, endY);
    const width = Math.abs(endX - startX);
    const height = Math.abs(endY - startY);
    
    if (width > 20 && height > 20) {
        pendingSelection = { x, y, width, height };
        
        clearOverlay();
        redrawSignatures(currentPage);
        showSelectionPreview(x, y, width, height);
    } else {
        alert('Bitte wählen Sie einen größeren Bereich für die Unterschrift aus.');
        
        clearOverlay();
        redrawSignatures(currentPage);
    }
}, { passive: false });

function initContractConfiguration(pdfUrl, csrfToken) {
    loadPdf(pdfUrl);
    
    updateWorkflowStep(1);
    
    if (pdfContainer && window.getComputedStyle(pdfContainer).position !== 'relative') {
        pdfContainer.style.position = 'relative';
    }
    if (!overlayCanvas) {
        console.error('Overlay canvas not found!');
        return;
    }
    
    overlayCanvas.addEventListener('mousedown', function(e) {
        if (!selectionMode) return;
        
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        
        const rect = overlayCanvas.getBoundingClientRect();
        startX = e.clientX - rect.left;
        startY = e.clientY - rect.top;
        isDrawing = true;
        
        hideSelectionPreview();
        
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
            pendingSelection = { x, y, width, height };
            
            clearOverlay();
            redrawSignatures(currentPage);
            showSelectionPreview(x, y, width, height);
        } else {
            alert('Bitte wählen Sie einen größeren Bereich für die Unterschrift aus.');
            clearOverlay();
            redrawSignatures(currentPage);
        }
    }, true);

    document.addEventListener('mousedown', function(e) {
        if (e.target === overlayCanvas && selectionMode) {
            e.preventDefault();
            e.stopPropagation();
            
            const rect = overlayCanvas.getBoundingClientRect();
            startX = e.clientX - rect.left;
            startY = e.clientY - rect.top;
            isDrawing = true;
            
            hideSelectionPreview();
            
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
                pendingSelection = { x, y, width, height };
                
                clearOverlay();
                redrawSignatures(currentPage);
                showSelectionPreview(x, y, width, height);
            } else {
                alert('Bitte wählen Sie einen größeren Bereich für die Unterschrift aus.');
                clearOverlay();
                redrawSignatures(currentPage);
            }
        }
    });
}