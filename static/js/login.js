document.addEventListener('DOMContentLoaded', function() {
    const connectButton = document.getElementById('connectButton');
    const loginButton = document.getElementById('loginButton');
    const errorMessage = document.getElementById('errorMessage');
    const successMessage = document.getElementById('successMessage');
    const walletInfo = document.getElementById('walletInfo');
    const walletAddress = document.getElementById('walletAddress');
    
    let currentAccount = null;
    
    // Check if MetaMask is installed
    if (typeof window.ethereum === 'undefined') {
        errorMessage.style.display = 'block';
        errorMessage.textContent = 'MetaMask ist nicht installiert. Bitte installieren Sie die MetaMask-Erweiterung.';
        connectButton.disabled = true;
    }
    
    // Connect to MetaMask
    connectButton.addEventListener('click', async function() {
        if (typeof window.ethereum !== 'undefined') {
            try {
                // Request account access
                const accounts = await ethereum.request({ method: 'eth_requestAccounts' });
                currentAccount = accounts[0];
                
                // Show wallet info
                walletAddress.textContent = `${currentAccount.substring(0, 6)}...${currentAccount.substring(38)}`;
                walletInfo.style.display = 'block';
                
                // Hide connect button and show login button
                connectButton.style.display = 'none';
                loginButton.style.display = 'flex';
                
            } catch (error) {
                console.error('User denied account access:', error);
                errorMessage.style.display = 'block';
                errorMessage.textContent = 'Zugriff auf die Wallet verweigert. Bitte erlauben Sie den Zugriff auf MetaMask.';
            }
        } else {
            errorMessage.style.display = 'block';
            errorMessage.textContent = 'MetaMask ist nicht installiert.';
        }
    });
    
    // Login with MetaMask
    loginButton.addEventListener('click', async function() {
        if (!currentAccount) return;
        
        try {
            // Get nonce from server
            const response = await fetch(`/auth/api/get_nonce/?address=${currentAccount}`);
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            const nonce = data.nonce;
            const message = `Sign this message to authenticate with our app: ${nonce}`;
            
            // Request signature from user
            const signature = await ethereum.request({
                method: 'personal_sign',
                params: [message, currentAccount]
            });
            
            // Verify signature with server
            const verifyResponse = await fetch('/auth/api/verify_signature/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    address: currentAccount,
                    signature: signature
                })
            });
            
            const verifyData = await verifyResponse.json();
            
            if (verifyData.success) {
                // Show success message
                successMessage.style.display = 'block';
                errorMessage.style.display = 'none';
                loginButton.style.display = 'none';
                
                // Redirect to main page after 2 seconds
                setTimeout(() => {
                    window.location.href = '/';
                }, 2000);
            } else {
                throw new Error(verifyData.error || 'Fehler bei der Verifikation');
            }
            
        } catch (error) {
            console.error('Error during login:', error);
            errorMessage.style.display = 'block';
            errorMessage.textContent = `Fehler beim Anmelden: ${error.message}`;
        }
    });
});
