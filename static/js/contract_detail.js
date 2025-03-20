// PDF.js initialisieren
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

// Elemente holen
const pdfViewer = document.getElementById('pdfViewer');
const prevPageBtn = document.getElementById('prevPage');
const nextPageBtn = document.getElementById('nextPage');
const currentPageNumSpan = document.getElementById('currentPageNum');
const totalPagesSpan = document.getElementById('totalPages');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingMessage = document.getElementById('loadingMessage');
const pdfContainer = document.getElementById('pdfContainer');

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
let pageNumPending = null;

// Render a page
const renderPage = (pageNum) => {
    pageRendering = true;
    showLoading('Seite wird geladen...');
    
    // Update the displayed page number
    currentPageNumSpan.textContent = pageNum;
    
    console.log(`Rendering page ${pageNum}`);
    
    // Get the page
    pdfDoc.getPage(pageNum).then(page => {
        console.log(`Got page ${pageNum}, rendering`);
        
        // Calculate scale to fit content within container width
        const containerWidth = pdfContainer.clientWidth;
        const originalViewport = page.getViewport({ scale: 1.0 });
        const scale = containerWidth / originalViewport.width;
        
        // Display viewport at calculated scale
        const viewport = page.getViewport({ scale: scale });
        
        pdfViewer.width = viewport.width;
        pdfViewer.height = viewport.height;
        
        const renderContext = {
            canvasContext: pdfViewer.getContext('2d'),
            viewport: viewport
        };
        
        // Clear canvas before rendering new page
        pdfViewer.getContext('2d').clearRect(0, 0, pdfViewer.width, pdfViewer.height);
        
        page.render(renderContext).promise.then(() => {
            pageRendering = false;
            hideLoading();
            
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
            console.log(`PDF loaded with ${doc.numPages} pages`);
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

// Window resize handler to make PDF responsive
window.addEventListener('resize', () => {
    if (pdfDoc) {
        queueRenderPage(currentPage);
    }
});

// Initialize function to set up everything
function initContractViewer(pdfUrl) {
    // Load PDF
    loadPdf(pdfUrl);
}
