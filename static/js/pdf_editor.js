document.addEventListener("DOMContentLoaded", function() {
    const contractAddress = window.pdfEditorConfig.contractAddress;
    // Rich Text Editor Setup
    const editor = document.getElementById('editor');
    const hiddenTextarea = document.getElementById('content');
    let undoStack = [];
    let redoStack = [];
    let currentUndoIndex = -1;

    // Einfache Template-Definitionen
    const templates = {
        'kaufvertrag': {
            name: 'Kaufvertrag',
            description: 'Für den Verkauf von Waren und Produkten',
            template: document.getElementById('kaufvertrag-template').innerHTML
        },
        'standard': {
            name: 'Allgemeiner Vertrag',
            description: 'Universelle Vorlage für alle Vertragsarten',
            template: document.getElementById('standard-template').innerHTML
        }
    };

    let currentTemplate = 'kaufvertrag';

    // Rich Text Editor Funktionen
    function saveToUndoStack() {
        undoStack.push(editor.innerHTML);
        redoStack = [];
        if (undoStack.length > 50) {
            undoStack.shift();
        }
        currentUndoIndex = undoStack.length - 1;
    }

    function updateHiddenTextarea() {
        hiddenTextarea.value = editor.innerHTML;
    }

    // Template-Auswahl
    document.querySelectorAll('.template-card').forEach(card => {
        card.addEventListener('click', function() {
            document.querySelectorAll('.template-card').forEach(c => c.classList.remove('active'));
            this.classList.add('active');
            
            currentTemplate = this.dataset.template;
            document.getElementById('contractType').value = currentTemplate;
            
            loadTemplate(currentTemplate);
        });
    });

    // Initiale Template-Ladung
    loadTemplate('kaufvertrag');
    document.querySelector('[data-template="kaufvertrag"]').classList.add('active');

    function loadTemplate(templateKey) {
        const template = templates[templateKey];
        if (!template) return;

        // Vertragsinhalt laden
        editor.innerHTML = template.template.replace('${contractAddress}', contractAddress);
        updateHiddenTextarea();
        
        // Titel vorschlagen
        const titleField = document.getElementById('title');
        if (!titleField.value.trim()) {
            titleField.value = template.name;
        }

        // Undo-Stack aktualisieren
        saveToUndoStack();
    }

    // Toolbar Event Listeners
    document.querySelectorAll('.toolbar-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const action = this.dataset.action;
            executeCommand(action);
        });
    });

    function executeCommand(command) {
        editor.focus();
        
        switch(command) {
            case 'bold':
                document.execCommand('bold', false, null);
                break;
            case 'italic':
                document.execCommand('italic', false, null);
                break;
            case 'underline':
                document.execCommand('underline', false, null);
                break;
            case 'heading':
                const selection = window.getSelection();
                if (selection.rangeCount > 0) {
                    const range = selection.getRangeAt(0);
                    const selectedText = range.toString();
                    if (selectedText) {
                        range.deleteContents();
                        const h3 = document.createElement('h3');
                        h3.textContent = selectedText;
                        range.insertNode(h3);
                        selection.removeAllRanges();
                    }
                }
                break;
            case 'paragraph':
                document.execCommand('formatBlock', false, 'p');
                break;
            case 'list':
                document.execCommand('insertUnorderedList', false, null);
                break;
            case 'number-list':
                document.execCommand('insertOrderedList', false, null);
                break;
            case 'center':
                const centerDiv = document.createElement('div');
                centerDiv.className = 'center-text';
                document.execCommand('insertHTML', false, centerDiv.outerHTML);
                break;
            case 'left':
                const leftDiv = document.createElement('div');
                leftDiv.className = 'left-text';
                document.execCommand('insertHTML', false, leftDiv.outerHTML);
                break;
            case 'placeholder':
                const placeholder = prompt('Platzhalter-Text eingeben:');
                if (placeholder) {
                    const span = `<span class="placeholder-field">${placeholder}</span>`;
                    document.execCommand('insertHTML', false, span);
                }
                break;
            case 'signature':
                const span = '<span class="signature-field"></span>';
                document.execCommand('insertHTML', false, span);
                break;
            case 'undo':
                if (currentUndoIndex > 0) {
                    currentUndoIndex--;
                    editor.innerHTML = undoStack[currentUndoIndex];
                    updateHiddenTextarea();
                }
                break;
            case 'redo':
                if (currentUndoIndex < undoStack.length - 1) {
                    currentUndoIndex++;
                    editor.innerHTML = undoStack[currentUndoIndex];
                    updateHiddenTextarea();
                }
                break;
        }
        
        updateHiddenTextarea();
        updateToolbarState();
        
        // Speichere Zustand für Undo/Redo (außer bei Undo/Redo selbst)
        if (command !== 'undo' && command !== 'redo') {
            saveToUndoStack();
        }
    }

    function updateToolbarState() {
        // Update active states für Format-Buttons
        document.querySelector('[data-action="bold"]').classList.toggle('active', document.queryCommandState('bold'));
        document.querySelector('[data-action="italic"]').classList.toggle('active', document.queryCommandState('italic'));
        document.querySelector('[data-action="underline"]').classList.toggle('active', document.queryCommandState('underline'));
    }

    // Quick Insert Funktionen
    window.insertQuickText = function(text) {
        editor.focus();
        document.execCommand('insertHTML', false, text);
        updateHiddenTextarea();
        saveToUndoStack();
    };

    // Contract-Adresse einfügen
    window.insertContractAddress = function() {
        editor.focus();
        const contractText = `<span class="placeholder-field">${contractAddress}</span>`;
        document.execCommand('insertHTML', false, contractText);
        updateHiddenTextarea();
        saveToUndoStack();
    };

    // Editor Event Listeners
    editor.addEventListener('input', function() {
        updateHiddenTextarea();
        saveToUndoStack();
    });

    editor.addEventListener('keyup', updateToolbarState);
    editor.addEventListener('mouseup', updateToolbarState);

    // Keyboard Shortcuts
    editor.addEventListener('keydown', function(e) {
        if (e.ctrlKey) {
            switch(e.key) {
                case 'b':
                    e.preventDefault();
                    executeCommand('bold');
                    break;
                case 'i':
                    e.preventDefault();
                    executeCommand('italic');
                    break;
                case 'u':
                    e.preventDefault();
                    executeCommand('underline');
                    break;
                case 'z':
                    e.preventDefault();
                    executeCommand('undo');
                    break;
                case 'y':
                    e.preventDefault();
                    executeCommand('redo');
                    break;
            }
        }
    });

    // Form-Submission
    document.getElementById('contractForm').addEventListener('submit', function(e) {
        const submitBtn = this.querySelector('button[type="submit"]');
        submitBtn.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>PDF wird erstellt...';
        submitBtn.disabled = true;
        
        // Validierung
        const title = document.getElementById('title').value.trim();
        const content = editor.innerHTML.trim();
        
        if (!title || !content || content === '<br>' || content === '') {
            e.preventDefault();
            alert('Bitte füllen Sie den Titel und den Vertragstext aus.');
            submitBtn.innerHTML = '<i class="bi bi-file-earmark-pdf me-2"></i>PDF erstellen und speichern';
            submitBtn.disabled = false;
            return;
        }

        // Final update der versteckten Textarea
        updateHiddenTextarea();
    });

    // Vorschau-Funktion
    window.previewContract = function() {
        const title = document.getElementById('title').value.trim();
        const content = editor.innerHTML.trim();

        if (!title) {
            alert('Bitte geben Sie einen Vertragstitel ein.');
            return;
        }

        if (!content || content === '<br>' || content === '') {
            alert('Bitte geben Sie Vertragsinhalt ein.');
            return;
        }

        document.getElementById('previewContent').innerHTML = `
            <h2 style="text-align: center; margin-bottom: 2rem; color: #0d6efd;">${title}</h2>
            <hr style="border-color: #0d6efd; margin-bottom: 2rem;">
            <div style="font-family: serif; line-height: 1.6;">${content}</div>
        `;

        new bootstrap.Modal(document.getElementById('previewModal')).show();
    };

    window.submitContract = function() {
        bootstrap.Modal.getInstance(document.getElementById('previewModal')).hide();
        document.getElementById('contractForm').submit();
    };

    // Platzhalter-Felder klickbar machen
    editor.addEventListener('click', function(e) {
        if (e.target.classList.contains('placeholder-field')) {
            const newText = prompt('Neuen Text eingeben:', e.target.textContent);
            if (newText !== null) {
                e.target.textContent = newText;
                updateHiddenTextarea();
                saveToUndoStack();
            }
        }
    });

    // Initiale Undo-Stack Einrichtung
    saveToUndoStack();
});
