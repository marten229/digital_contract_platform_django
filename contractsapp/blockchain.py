from web3 import Web3
import json
import hashlib
from django.conf import settings
import os

class BlockchainService:
    """Service for interacting with the Ethereum blockchain and smart contracts"""
    
    def __init__(self):
        # Connect to an Ethereum node - replace with your actual provider URL
        # For development, you might use Ganache, Infura, or Alchemy
        self.web3 = Web3(Web3.HTTPProvider(getattr(settings, 'ETHEREUM_NODE_URL', 'http://localhost:8545')))
        
        # Load contract ABI and address from settings or environment variables
        self.contract_abi = self._load_contract_abi()
        
        # Dynamische Verwaltung der Contract-Adresse
        # Von den Einstellungen laden, falls verfügbar
        self.contract_address = getattr(settings, 'CONTRACT_ADDRESS', None)
        
        # Contract-Instanz initialisieren, falls eine Adresse verfügbar ist
        self.contract = None
        if self.contract_address and self.web3.is_address(self.contract_address):
            self._initialize_contract()
    
    def _initialize_contract(self):
        """Initialisiert den Smart Contract mit der aktuellen Adresse"""
        if self.contract_address and self.contract_abi:
            self.contract = self.web3.eth.contract(
                address=self.contract_address,
                abi=self.contract_abi
            )
            return True
        return False
    
    def _load_contract_abi(self):
        """Load contract ABI from file"""
        try:
            abi_path = getattr(settings, 'CONTRACT_ABI_PATH', 
                              os.path.join(settings.BASE_DIR, 'contractsapp', 'static', 'contracts', 'DigitalContractPlatform.json'))
            
            with open(abi_path, 'r') as file:
                contract_data = json.load(file)
                return contract_data['abi']
        except Exception as e:
            print(f"Error loading contract ABI: {e}")
            return None
    
    def deploy_contract(self, deployer_address):
        """Deploy a new contract to the blockchain and return its address"""
        if not self.contract_abi:
            raise ValueError("Contract ABI not properly loaded")
            
        # Get the bytecode from the JSON file
        try:
            abi_path = getattr(settings, 'CONTRACT_ABI_PATH', 
                               os.path.join(settings.BASE_DIR, 'contractsapp', 'static', 'contracts', 'DigitalContractPlatform.json'))
            
            with open(abi_path, 'r') as file:
                contract_data = json.load(file)
                bytecode = contract_data.get('bytecode')
                
                if not bytecode:
                    raise ValueError("Bytecode not found in contract JSON file")
        except Exception as e:
            raise ValueError(f"Failed to load contract bytecode: {e}")
        
        # Create the contract object without an address
        contract = self.web3.eth.contract(abi=self.contract_abi, bytecode=bytecode)
        
        # Get current gas price and increase it by 50% to ensure faster mining
        gas_price = self.web3.eth.gas_price
        increased_gas_price = int(gas_price * 1.5)
        
        # Prepare transaction to deploy the contract with higher gas price
        tx = contract.constructor().build_transaction({
            'from': deployer_address,
            'nonce': self.web3.eth.get_transaction_count(deployer_address),
            'gas': 5000000,  # Increased gas limit
            'gasPrice': increased_gas_price
        })
        
        # Return the transaction for signing in the frontend
        # After the transaction is signed and confirmed, the address
        # will be available in the transaction receipt
        return tx
    
    def set_contract_address(self, address):
        """Set the contract address and initialize the contract"""
        if self.web3.is_address(address):
            self.contract_address = address
            return self._initialize_contract()
        return False
    
    def get_contract_address(self):
        """Get the current contract address"""
        return self.contract_address
        
    def calculate_pdf_hash(self, pdf_file):
        """Calculate SHA-256 hash of a PDF file"""
        sha256_hash = hashlib.sha256()
        
        # If it's a Django File object
        if hasattr(pdf_file, 'read'):
            # Save current position
            if hasattr(pdf_file, 'tell'):
                current_position = pdf_file.tell()
            else:
                current_position = 0
                
            # Reset to beginning
            pdf_file.seek(0)
            
            # Read in chunks to handle large files
            for byte_block in iter(lambda: pdf_file.read(4096), b""):
                sha256_hash.update(byte_block)
                
            # Restore position
            pdf_file.seek(current_position)
        # If it's a path
        elif isinstance(pdf_file, str) and os.path.exists(pdf_file):
            with open(pdf_file, 'rb') as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
        else:
            raise ValueError("Invalid file input")
            
        return '0x' + sha256_hash.hexdigest()
    
    def create_contract(self, creator_address, counterparty_address, contract_hash, amount_wei):
        """Create a new contract on the blockchain"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Prepare the transaction
        tx = self.contract.functions.createContract(
            counterparty_address,
            contract_hash,
            amount_wei
        ).build_transaction({
            'from': creator_address,
            'value': amount_wei,
            'nonce': self.web3.eth.get_transaction_count(creator_address),
            'gas': 2000000,  # Adjust as needed
            'gasPrice': self.web3.eth.gas_price
        })
        
        # The transaction needs to be signed by the creator off-chain
        # Return the transaction for signing in the frontend
        return tx
    
    def sign_contract(self, partner_address, contract_id):
        """Sign a contract on the blockchain"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Prepare the transaction
        tx = self.contract.functions.signContract(contract_id).build_transaction({
            'from': partner_address,
            'nonce': self.web3.eth.get_transaction_count(partner_address),
            'gas': 2000000,  # Adjust as needed
            'gasPrice': self.web3.eth.gas_price
        })
        
        # Return the transaction for signing in the frontend
        return tx
    
    def confirm_completion(self, creator_address, contract_id):
        """Confirm contract completion on the blockchain"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Prepare the transaction
        tx = self.contract.functions.confirmCompletion(contract_id).build_transaction({
            'from': creator_address,
            'nonce': self.web3.eth.get_transaction_count(creator_address),
            'gas': 2000000,  # Adjust as needed
            'gasPrice': self.web3.eth.gas_price
        })
        
        # Return the transaction for signing in the frontend
        return tx
    
    def get_contract_status(self, contract_id):
        """Get the status of a contract from the blockchain"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
            
        status = self.contract.functions.getContractStatus(contract_id).call()
        status_map = {
            0: 'Created',
            1: 'Signed',
            2: 'Completed',
            3: 'Cancelled'
        }
        return status_map.get(status, 'Unknown')
    
    def get_contract_hash(self, contract_id):
        """Get the contract hash from the blockchain"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
            
        return self.contract.functions.getContractIPFSHash(contract_id).call()
        
    def withdrawFunds(self, partner_address):
        """Withdraw available funds from the contract"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Prepare the withdrawal transaction
        tx = self.contract.functions.withdrawFunds().build_transaction({
            'from': partner_address,
            'nonce': self.web3.eth.get_transaction_count(partner_address),
            'gas': 2000000,  # Adjust as needed
            'gasPrice': self.web3.eth.gas_price
        })
        
        # Return the transaction for signing in the frontend
        return tx