pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

const pdfViewer = document.getElementById('pdfViewer');
const prevPageBtn = document.getElementById('prevPage');
const nextPageBtn = document.getElementById('nextPage');
const currentPageNumSpan = document.getElementById('currentPageNum');
const totalPagesSpan = document.getElementById('totalPages');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingMessage = document.getElementById('loadingMessage');
const pdfContainer = document.getElementById('pdfContainer');

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
let pageNumPending = null;

const renderPage = (pageNum) => {
    pageRendering = true;
    showLoading('Seite wird geladen...');
    
    currentPageNumSpan.textContent = pageNum;
    
    console.log(`Rendering page ${pageNum}`);

    pdfDoc.getPage(pageNum).then(page => {
        console.log(`Got page ${pageNum}, rendering`);
        
        const containerWidth = pdfContainer.clientWidth;
        const originalViewport = page.getViewport({ scale: 1.0 });
        const scale = containerWidth / originalViewport.width;
        
        const viewport = page.getViewport({ scale: scale });
        
        pdfViewer.width = viewport.width;
        pdfViewer.height = viewport.height;
        
        const renderContext = {
            canvasContext: pdfViewer.getContext('2d'),
            viewport: viewport
        };
        
        pdfViewer.getContext('2d').clearRect(0, 0, pdfViewer.width, pdfViewer.height);
        
        page.render(renderContext).promise.then(() => {
            pageRendering = false;
            hideLoading();
            
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
            console.log(`PDF loaded with ${doc.numPages} pages`);
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

prevPageBtn.addEventListener('click', () => {
    if (currentPage <= 1) return;
    currentPage--;
    queueRenderPage(currentPage);
    
    prevPageBtn.disabled = (currentPage <= 1);
    nextPageBtn.disabled = (currentPage >= pdfDoc.numPages);
});

nextPageBtn.addEventListener('click', () => {
    if (currentPage >= pdfDoc.numPages) return;
    currentPage++;
    queueRenderPage(currentPage);
    
    prevPageBtn.disabled = (currentPage <= 1);
    nextPageBtn.disabled = (currentPage >= pdfDoc.numPages);
});

window.addEventListener('resize', () => {
    if (pdfDoc) {
        queueRenderPage(currentPage);
    }
});

function initContractViewer(pdfUrl) {
    loadPdf(pdfUrl);
}
