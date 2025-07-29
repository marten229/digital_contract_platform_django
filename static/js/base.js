document.addEventListener('DOMContentLoaded', function() {
    const toasts = document.querySelectorAll('.toast');

    toasts.forEach((toast) => {
        const bsToast = new bootstrap.Toast(toast, {
            animation: true,
            autohide: true,
            delay: 5000
        });
        bsToast.show();
    });

    const navbar = document.querySelector('.navbar');

    window.addEventListener('scroll', function() {
        if (window.scrollY > 50) {
            navbar.classList.add('navbar-scrolled');
        } else {
            navbar.classList.remove('navbar-scrolled');
        }
    });
});
