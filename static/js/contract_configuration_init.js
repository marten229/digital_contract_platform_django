document.addEventListener('DOMContentLoaded', function() {
    const dhlCheckbox = document.getElementById('hasDhlTracking');
    const dhlFields = document.getElementById('dhlTrackingFields');

    if (dhlCheckbox && dhlFields) {
        dhlCheckbox.addEventListener('change', function() {
            if (this.checked) {
                dhlFields.style.display = 'block';
            } else {
                dhlFields.style.display = 'none';
            }
        });
    }

    if (window.contractConfig) {
        initContractConfiguration(
            window.contractConfig.pdfUrl,
            window.contractConfig.csrfToken
        );
    }
});
