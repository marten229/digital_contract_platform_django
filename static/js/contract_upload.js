document.addEventListener('DOMContentLoaded', function() {
    const uploadRadio = document.getElementById('upload_new');
    const uploadArea = document.getElementById('upload_area');
    const pdfRadios = document.querySelectorAll('input[name="selected_pdf"]:not(#upload_new)');
    const fileInput = document.querySelector('input[type="file"]');

    function toggleUploadArea() {
        if (uploadRadio.checked) {
            uploadArea.style.display = 'block';
            fileInput.required = true;
        } else {
            uploadArea.style.display = 'none';
            fileInput.required = false;
            fileInput.value = '';
        }
    }

    uploadRadio.addEventListener('change', toggleUploadArea);
    pdfRadios.forEach(radio => {
        radio.addEventListener('change', toggleUploadArea);
    });

    toggleUploadArea();

    document.querySelectorAll('input[name="selected_pdf"]').forEach(radio => {
        radio.addEventListener('change', function() {
            document.querySelectorAll('.created-pdf-option').forEach(option => {
                option.classList.remove('selected');
            });
            if (this.value !== 'upload_new') {
                const label = this.closest('.form-check').querySelector('.created-pdf-option');
                if (label) {
                    label.classList.add('selected');
                }
            }
        });
    });
});
