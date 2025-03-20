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
