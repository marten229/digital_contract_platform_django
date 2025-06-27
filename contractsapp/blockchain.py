from web3 import Web3
import json
import hashlib
from django.conf import settings
import os

class BlockchainService:
    """Service for interacting with the Ethereum blockchain and smart contracts"""
    
    def __init__(self):
        # Connect to an Ethereum node - replace with your actual provider URL
        ethereum_node_url = getattr(settings, 'ETHEREUM_NODE_URL', 'http://localhost:8545')
        
        # Stelle sicher, dass die URL korrekt formatiert ist (mit http/https Präfix)
        if not ethereum_node_url.startswith('http'):
            ethereum_node_url = 'https://' + ethereum_node_url
            
        self.web3 = Web3(Web3.HTTPProvider(ethereum_node_url))
        
        # Load contract ABI and address from settings or environment variables
        self.contract_abi = self._load_contract_abi()
        
        # Dynamische Verwaltung der Contract-Adresse
        # Von den Einstellungen laden, falls verfügbar
        self.contract_address = getattr(settings, 'CONTRACT_ADDRESS', None)
        
        # Contract-Instanz initialisieren, falls eine Adresse verfügbar ist
        self.contract = None
        if self.contract_address:
            # Stelle sicher, dass die Adresse das korrekte Format hat (mit 0x Präfix)
            if not self.contract_address.startswith('0x'):
                self.contract_address = '0x' + self.contract_address
                
            if self.web3.is_address(self.contract_address):
                self._initialize_contract()
            else:
                print(f"Warnung: Ungültige Ethereum-Adresse: {self.contract_address}")
    
    def _initialize_contract(self):
        """Initialisiert den Smart Contract mit der aktuellen Adresse"""
        if self.contract_address and self.contract_abi:
            try:
                self.contract = self.web3.eth.contract(
                    address=self.contract_address,
                    abi=self.contract_abi
                )
                return True
            except Exception as e:
                print(f"Fehler bei der Contract-Initialisierung: {str(e)}")
                return False
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
    
    def calculate_tracking_hash(self, tracking_number, contract_id=None):
        """
        Generate a hashed value of the tracking number for blockchain storage
        Uses keccak256 hashing to match the smart contract requirements
        
        Args:
            tracking_number: DHL tracking number (wird normalisiert)
            contract_id: Blockchain contract ID (required for proper hash verification)
        """
        if contract_id is None:
            raise ValueError("contract_id is required for tracking hash generation")
        
        # Tracking-Nummer normalisieren (Leerzeichen entfernen) - WICHTIG für Hash-Konsistenz
        tracking_number = tracking_number.strip() if tracking_number else ""
        
        if not tracking_number:
            raise ValueError("Tracking-Nummer darf nicht leer sein")
        
        # Use keccak256 hash like the smart contract expects
        from web3 import Web3
        
        # Create Web3 instance just for hash calculation
        web3_instance = Web3()
        
        # Calculate keccak256 hash of tracking number
        tracking_bytes = tracking_number.encode('utf-8')
        hash_value = web3_instance.keccak(tracking_bytes)
        
        # Return as 0x-prefixed hex string
        return hash_value
    
    def create_contract(self, creator_address, counterparty_address, contract_hash, amount_wei):
        """Create a new contract on the blockchain"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Ensure addresses are in checksum format
        try:
            # Stelle sicher, dass die Adressen nicht None oder leer sind
            if not creator_address or not counterparty_address:
                raise ValueError("Creator or counterparty address is empty")
                
            # Stelle sicher, dass die Adressen mit 0x beginnen
            if not creator_address.startswith('0x'):
                creator_address = '0x' + creator_address
            if not counterparty_address.startswith('0x'):
                counterparty_address = '0x' + counterparty_address
                
            creator_address = self.web3.to_checksum_address(creator_address)
            counterparty_address = self.web3.to_checksum_address(counterparty_address)
        except ValueError as e:
            raise ValueError(f"Invalid Ethereum address: {str(e)}")
        
        # Convert contract hash to bytes32 format for smart contract
        if contract_hash.startswith('0x'):
            contract_hash_bytes = bytes.fromhex(contract_hash[2:])
        else:
            contract_hash_bytes = bytes.fromhex(contract_hash)
        
        # Prepare the transaction
        tx = self.contract.functions.createContract(
            counterparty_address,
            contract_hash_bytes,
            amount_wei
        ).build_transaction({
            'from': creator_address,
            'value': amount_wei,
            'nonce': self.web3.eth.get_transaction_count(creator_address),
            'gas': 2000000,  # Adjust as needed
            'gasPrice': self.web3.eth.gas_price
        })
        
        # Return the transaction for signing in the frontend
        # The contract ID will be extracted from the ContractCreated event after the transaction is confirmed
        return tx
    
    def sign_contract(self, partner_address, contract_id):
        """Sign a contract on the blockchain"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Ensure address is in checksum format
        try:
            # Stelle sicher, dass die Adresse nicht None oder leer ist
            if not partner_address:
                raise ValueError("Partner address is empty")
                
            # Stelle sicher, dass die Adresse mit 0x beginnt
            if not partner_address.startswith('0x'):
                partner_address = '0x' + partner_address
                
            partner_address = self.web3.to_checksum_address(partner_address)
        except ValueError as e:
            raise ValueError(f"Invalid Ethereum address: {str(e)}")
        
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
        
        # Ensure address is in checksum format
        try:
            # Stelle sicher, dass die Adresse nicht None oder leer ist
            if not creator_address:
                raise ValueError("Creator address is empty")
                
            # Stelle sicher, dass die Adresse mit 0x beginnt
            if not creator_address.startswith('0x'):
                creator_address = '0x' + creator_address
                
            creator_address = self.web3.to_checksum_address(creator_address)
        except ValueError as e:
            raise ValueError(f"Invalid Ethereum address: {str(e)}")
        
        # Prepare the transaction to confirm completion - this will set the contract as completed
        # in the Contract Manager
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
            2: 'DeliverySet',
            3: 'DeliveryConfirmed',
            4: 'DeliveryApproved',
            5: 'AgreementFulfilled',
            6: 'Completed',
            7: 'Cancelled'
        }
        return status_map.get(status, 'Unknown')
    
        
    def withdrawFunds(self, partner_address, contract_id):
        """Withdraw available funds from the contract"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Ensure address is in checksum format
        try:
            # Stelle sicher, dass die Adresse nicht None oder leer ist
            if not partner_address:
                raise ValueError("Partner address is empty")
                
            # Stelle sicher, dass die Adresse mit 0x beginnt
            if not partner_address.startswith('0x'):
                partner_address = '0x' + partner_address
                
            partner_address = self.web3.to_checksum_address(partner_address)
        except ValueError as e:
            raise ValueError(f"Invalid Ethereum address: {str(e)}")
        
        # Prepare the withdrawal transaction - using the new method name from the contract
        tx = self.contract.functions.withdrawFundsFrom(contract_id).build_transaction({
            'from': partner_address,
            'nonce': self.web3.eth.get_transaction_count(partner_address),
            'gas': 2000000,  # Adjust as needed
            'gasPrice': self.web3.eth.gas_price
        })
        
        # Return the transaction for signing in the frontend
        return tx
        
    def get_contract_details(self, contract_id):
        """Get all details for a specific contract from the Contract Manager"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
            
        contract_details = self.contract.functions.contracts(contract_id).call()
        
        # Format the contract details based on the Solidity contract structure
        formatted_details = {
            'id': contract_details[0],
            'amount': contract_details[1],
            'creator': contract_details[2],
            'counterparty': contract_details[3],
            'status': self.get_contract_status(contract_id),
            'hash': contract_details[5]
        }
        
        return formatted_details
    
    def deactivate_contract(self, creator_address, contract_id):
        """Deactivate (void) a contract on the blockchain"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Ensure address is in checksum format
        try:
            # Stelle sicher, dass die Adresse nicht None oder leer ist
            if not creator_address:
                raise ValueError("Creator address is empty")
                
            # Stelle sicher, dass die Adresse mit 0x beginnt
            if not creator_address.startswith('0x'):
                creator_address = '0x' + creator_address
                
            creator_address = self.web3.to_checksum_address(creator_address)
        except ValueError as e:
            raise ValueError(f"Invalid Ethereum address: {str(e)}")
        
        # Prepare the transaction to deactivate the contract
        tx = self.contract.functions.deactivateContract(contract_id).build_transaction({
            'from': creator_address,
            'nonce': self.web3.eth.get_transaction_count(creator_address),
            'gas': 2000000,  # Adjust as needed
            'gasPrice': self.web3.eth.gas_price        })
        
        # Return the transaction for signing in the frontend
        return tx
        
    def set_delivery_tracking(self, partner_address, contract_id, tracking_number):
        """Set the delivery tracking hash for a contract on the blockchain"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Ensure address is in checksum format
        try:
            # Stelle sicher, dass die Adresse nicht None oder leer ist
            if not partner_address:
                raise ValueError("Partner address is empty")
                
            # Stelle sicher, dass die Adresse mit 0x beginnt
            if not partner_address.startswith('0x'):
                partner_address = '0x' + partner_address
                
            partner_address = self.web3.to_checksum_address(partner_address)
        except ValueError as e:
            raise ValueError(f"Invalid Ethereum address: {str(e)}")
        
        # Convert tracking number to bytes32 hash for privacy
        tracking_hash = self.calculate_tracking_hash(tracking_number, contract_id)

        # Convert hash to bytes32 format for smart contract
        if isinstance(tracking_hash, bytes):
            tracking_hash_bytes = tracking_hash
        else:
            if tracking_hash.startswith('0x'):
                tracking_hash_bytes = bytes.fromhex(tracking_hash[2:])
            else:
                tracking_hash_bytes = bytes.fromhex(tracking_hash)
        
        # Prepare the transaction to set delivery tracking
        tx = self.contract.functions.setDeliveryTracking(contract_id, tracking_hash_bytes).build_transaction({
            'from': partner_address,
            'nonce': self.web3.eth.get_transaction_count(partner_address),
            'gas': 2000000,
            'gasPrice': self.web3.eth.gas_price
        })
        
        return {
            'success': True,
            'transaction': tx,
            'message': f'Tracking hash prepared for blockchain'
        }
        
    def confirm_delivery_by_oracle(self, oracle_address, contract_id, tracking_hash):
        """Confirm delivery by the Oracle on the blockchain"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Ensure address is in checksum format
        try:
            # Stelle sicher, dass die Adresse nicht None oder leer ist
            if not oracle_address:
                raise ValueError("Oracle address is empty")
                
            # Stelle sicher, dass die Adresse mit 0x beginnt
            if not oracle_address.startswith('0x'):
                oracle_address = '0x' + oracle_address
                
            oracle_address = self.web3.to_checksum_address(oracle_address)
        except ValueError as e:
            raise ValueError(f"Invalid Ethereum address: {str(e)}")
        
        # Convert tracking hash to bytes32 format for smart contract
        if isinstance(tracking_hash, bytes):
            tracking_hash_bytes = tracking_hash
        else:
            if tracking_hash.startswith('0x'):
                tracking_hash_bytes = bytes.fromhex(tracking_hash[2:])
            else:
                tracking_hash_bytes = bytes.fromhex(tracking_hash)
        
        # Prepare the transaction to confirm delivery by Oracle
        tx = self.contract.functions.confirmDeliveryByOracle(contract_id, tracking_hash_bytes).build_transaction({
            'from': oracle_address,
            'nonce': self.web3.eth.get_transaction_count(oracle_address),
            'gas': 2000000,
            'gasPrice': self.web3.eth.gas_price
        })
        
        # Return the transaction for signing in the frontend
        return tx
    
    def approve_delivery_as_creator(self, creator_address, contract_id):
        """Approve delivery as the contract creator"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Ensure address is in checksum format
        try:
            if not creator_address:
                raise ValueError("Creator address is empty")
                
            if not creator_address.startswith('0x'):
                creator_address = '0x' + creator_address
                
            creator_address = self.web3.to_checksum_address(creator_address)
        except ValueError as e:
            raise ValueError(f"Invalid Ethereum address: {str(e)}")
        
        # Prepare the transaction to approve delivery
        tx = self.contract.functions.approveDeliveryAsCreator(contract_id).build_transaction({
            'from': creator_address,
            'nonce': self.web3.eth.get_transaction_count(creator_address),
            'gas': 2000000,
            'gasPrice': self.web3.eth.gas_price
        })
        
        return tx
    
    def get_withdrawal_balance(self, address):
        """Get the pending withdrawal balance for an address"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        try:
            if not address.startswith('0x'):
                address = '0x' + address
                
            address = self.web3.to_checksum_address(address)
        except ValueError as e:
            raise ValueError(f"Invalid Ethereum address: {str(e)}")
        
        balance = self.contract.functions.pendingWithdrawals(address).call()
        return balance

    def get_contract_details_extended(self, contract_id):
        """Get extended contract details including delivery status"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
            
        contract_details = self.contract.functions.contracts(contract_id).call()
        # Format the contract details based on the new Solidity contract structure
        
        # Properly handle deliveryTrackingHash conversion from bytes32 to hex string
        delivery_tracking_hash = contract_details[6]
        if delivery_tracking_hash and delivery_tracking_hash != b'\x00' * 32:
            # Convert bytes32 to hex string
            if isinstance(delivery_tracking_hash, bytes):
                delivery_tracking_hash = '0x' + delivery_tracking_hash.hex()
            else:
                delivery_tracking_hash = str(delivery_tracking_hash)
        else:
            delivery_tracking_hash = None        
        formatted_details = {
            'id': contract_details[0],
            'amount': contract_details[1],
            'creator': contract_details[2],
            'counterparty': contract_details[3],
            'status': self.get_contract_status(contract_id),
            'contractHash': contract_details[5],
            'deliveryTrackingHash': delivery_tracking_hash,
            'deliveryRequired': contract_details[7]
        }
        
        return formatted_details
    
    def set_oracle(self, deployer_address, oracle_address):
        """Set the oracle address for the contract"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        # Ensure addresses are in checksum format
        try:
            if not deployer_address or not oracle_address:
                raise ValueError("Deployer or oracle address is empty")
                
            if not deployer_address.startswith('0x'):
                deployer_address = '0x' + deployer_address
            if not oracle_address.startswith('0x'):
                oracle_address = '0x' + oracle_address
                
            deployer_address = self.web3.to_checksum_address(deployer_address)
            oracle_address = self.web3.to_checksum_address(oracle_address)
        except ValueError as e:
            raise ValueError(f"Invalid Ethereum address: {str(e)}")
        
        # Prepare the transaction to set oracle
        tx = self.contract.functions.setOracle(oracle_address).build_transaction({
            'from': deployer_address,
            'nonce': self.web3.eth.get_transaction_count(deployer_address),
            'gas': 2000000,
            'gasPrice': self.web3.eth.gas_price
        })
        
        return tx
    
    def extract_contract_id_from_receipt(self, tx_receipt):
        """Extract the contract ID from the ContractCreated event in the transaction receipt"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
        
        try:
            # Get the ContractCreated event from the receipt
            contract_created_filter = self.contract.events.ContractCreated.create_filter(
                fromBlock=tx_receipt['blockNumber'],
                toBlock=tx_receipt['blockNumber']
            )
            
            # Process the receipt to get events
            events = self.contract.events.ContractCreated().process_receipt(tx_receipt)
            
            if events:
                # Return the contract ID from the first (and should be only) event
                contract_id = events[0]['args']['contractId']
                print(f"Contract ID aus Event extrahiert: {contract_id}")
                return contract_id
            else:
                print("Kein ContractCreated Event in der Transaction gefunden")
                return None
                
        except Exception as e:
            print(f"Fehler beim Extrahieren der Contract ID: {str(e)}")
            return None
    
    def get_contract_id_from_tx_hash(self, tx_hash):
        """Get contract ID from a transaction hash by checking the transaction receipt"""
        try:
            receipt = self.web3.eth.get_transaction_receipt(tx_hash)
            return self.extract_contract_id_from_receipt(receipt)
        except Exception as e:
            print(f"Fehler beim Abrufen der Contract ID aus TX Hash {tx_hash}: {str(e)}")
            return None