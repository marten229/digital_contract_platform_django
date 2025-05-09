document.addEventListener('DOMContentLoaded', function() {
    const connectButton = document.getElementById('connectButton');
    const loginButton = document.getElementById('loginButton');
    const errorMessage = document.getElementById('errorMessage');
    const successMessage = document.getElementById('successMessage');
    const walletInfo = document.getElementById('walletInfo');
    const walletAddress = document.getElementById('walletAddress');
    const accountSelectionContainer = document.getElementById('accountSelectionContainer');
    const accountsList = document.getElementById('accountsList');
    
    let accounts = [];
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
                accounts = await ethereum.request({ method: 'eth_requestAccounts' });
                
                if (accounts.length === 1) {
                    // If there's only one account, select it automatically
                    selectAccount(accounts[0]);
                    connectButton.style.display = 'none';
                } else {
                    // Display accounts for selection
                    displayAccounts();
                    connectButton.style.display = 'none';
                }
                
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
    
    // Function to display accounts for selection
    function displayAccounts() {
        accountsList.innerHTML = '';
        accounts.forEach(account => {
            const accountItem = document.createElement('div');
            accountItem.className = 'account-item';
            accountItem.innerHTML = `
                <input type="radio" name="account" id="account-${account}" value="${account}">
                <label for="account-${account}">
                    ${account.substring(0, 6)}...${account.substring(38)}
                </label>
            `;
            accountsList.appendChild(accountItem);
        });
        
        accountSelectionContainer.style.display = 'block';
    }
    
    // Handle account selection
    accountsList.addEventListener('click', function(event) {
        const radioInput = event.target.closest('.account-item').querySelector('input[type="radio"]');
        if (radioInput) {
            radioInput.checked = true;
            selectAccount(radioInput.value);
        }
    });
    
    // Function to select an account
    function selectAccount(account) {
        currentAccount = account;
        walletAddress.textContent = `${account.substring(0, 6)}...${account.substring(38)}`;
        walletInfo.style.display = 'block';
        loginButton.style.display = 'flex';
    }
      // Login with MetaMask
    loginButton.addEventListener('click', async function() {
        if (!currentAccount) return;
        
        try {
            // Clear any previous error messages
            errorMessage.style.display = 'none';
            
            console.log('Starting login process with account:', currentAccount);
            
            // Get nonce from server
            console.log('Fetching nonce from server...');
            const response = await fetch(`/auth/api/get_nonce/?address=${currentAccount}`);
            const data = await response.json();
            console.log('Received nonce response:', data);
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            const nonce = data.nonce;
            const message = `Sign this message to authenticate with our app: ${nonce}`;
            console.log('Message to sign:', message);
            
            // Request signature from user
            console.log('Requesting signature from MetaMask...');
            let signature;
            try {
                signature = await ethereum.request({
                    method: 'personal_sign',
                    params: [message, currentAccount]
                });
                console.log('Signature received:', signature);
            } catch (signError) {
                console.error('Error during signing:', signError);
                throw new Error(`Signatur-Fehler: ${signError.message || 'Unbekannter Fehler beim Signieren'}`);
            }
            
            if (!signature) {
                throw new Error('Keine Signatur erhalten');
            }
            
            // Verify signature with server
            console.log('Sending signature to server for verification...');
            const payload = {
                address: currentAccount,
                signature: signature
            };
            console.log('Payload:', payload);
            
            const verifyResponse = await fetch('/auth/api/verify_signature/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });
            
            console.log('Server response status:', verifyResponse.status);
            const verifyData = await verifyResponse.json();
            console.log('Verification response:', verifyData);
            
            if (verifyData.success) {
                // Show success message
                successMessage.style.display = 'block';
                errorMessage.style.display = 'none';
                loginButton.style.display = 'none';
                
                // Redirect to main page after 2 seconds
                setTimeout(() => {
                    window.location.href = '/dashboard/';
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
