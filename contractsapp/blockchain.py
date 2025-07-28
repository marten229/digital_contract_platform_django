from web3 import Web3
import json
import hashlib
from django.conf import settings
import os
from typing import Dict, Any, Optional, Union


class BlockchainService:
    """Service for interacting with the Ethereum blockchain and smart contracts"""
    
    DEFAULT_GAS_LIMIT = 2000000
    DEPLOYMENT_GAS_LIMIT = 5000000
    GAS_PRICE_MULTIPLIER = 1.5
    
    CONTRACT_STATUS_MAP = {
        0: 'Created',
        1: 'Signed',
        2: 'DeliverySet',
        3: 'DeliveryConfirmed',
        4: 'DeliveryApproved',
        5: 'AgreementFulfilled',
        6: 'Completed',
        7: 'Cancelled'
    }
    
    def __init__(self):
        """Initialize blockchain service with Web3 connection and contract setup"""
        self.web3 = self._initialize_web3()
        self.contract_abi = self._load_contract_abi()
        self.contract_address = getattr(settings, 'CONTRACT_ADDRESS', None)
        self.contract = None
        
        if self.contract_address:
            self._setup_contract()
    
    def _initialize_web3(self) -> Web3:
        """Initialize Web3 connection"""
        ethereum_node_url = getattr(settings, 'ETHEREUM_NODE_URL', 'http://localhost:8545')
        
        if not ethereum_node_url.startswith('http'):
            ethereum_node_url = f'https://{ethereum_node_url}'
            
        return Web3(Web3.HTTPProvider(ethereum_node_url))
    
    def _setup_contract(self) -> bool:
        """Setup contract instance with validation"""
        if not self.contract_address or not self.contract_abi:
            return False     
        try:
            self.contract_address = self._format_address(self.contract_address)
            
            if not self.web3.is_address(self.contract_address):
                return False
                
            self.contract = self.web3.eth.contract(
                address=self.contract_address,
                abi=self.contract_abi
            )
            return True
            
        except Exception as e:
            return False
    
    def _load_contract_abi(self) -> Optional[list]:
        """Load contract ABI from JSON file with error handling"""
        try:
            abi_path = getattr(
                settings, 
                'CONTRACT_ABI_PATH',
                os.path.join(settings.BASE_DIR, 'contractsapp', 'static', 'contracts', 'DigitalContractPlatform.json')
            )
            
            with open(abi_path, 'r') as file:
                contract_data = json.load(file)
                return contract_data['abi']
                
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            return None
    
    def _validate_contract_initialized(self):
        """Validate that smart contract is properly initialized"""
        if not self.contract:
            raise ValueError("Smart contract not properly initialized")
    
    def _format_address(self, address: str) -> str:
        """Format Ethereum address with proper 0x prefix"""
        if not address:
            raise ValueError("Address cannot be empty")
        
        if not address.startswith('0x'):
            address = f'0x{address}'
            
        return address
    
    def _validate_and_format_address(self, address: str, address_type: str = "address") -> str:
        """Validate and format Ethereum address with descriptive error messages"""
        if not address:
            raise ValueError(f"{address_type} cannot be empty")
        
        try:
            formatted_address = self._format_address(address)
            return self.web3.to_checksum_address(formatted_address)
        except ValueError as e:
            raise ValueError(f"Invalid {address_type}: {str(e)}")
    
    
    def _convert_to_bytes32(self, hex_string: str) -> bytes:
        """Convert hex string to bytes32 format for smart contract"""
        if isinstance(hex_string, bytes):
            return hex_string
        
        if hex_string.startswith('0x'):
            return bytes.fromhex(hex_string[2:])
        else:
            return bytes.fromhex(hex_string)
    
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
    
    def create_contract(self, creator_address: str, counterparty_address: str, 
                       contract_hash: str, amount_wei: int) -> Dict[str, Any]:
        """Create a new contract instance inside the Smart Contract"""
        self._validate_contract_initialized()
        
        creator_address = self._validate_and_format_address(creator_address, "Creator address")
        counterparty_address = self._validate_and_format_address(counterparty_address, "Counterparty address")
        
        contract_hash_bytes = self._convert_to_bytes32(contract_hash)
        
        tx_params = self._prepare_transaction_base(creator_address)
        tx_params['value'] = amount_wei
        
        try:
            tx = self.contract.functions.createContract(
                counterparty_address,
                contract_hash_bytes,
                amount_wei
            ).build_transaction(tx_params)
            
            return tx
            
        except Exception as e:
            raise ValueError(f"Failed to create contract transaction: {str(e)}")
        
    def _prepare_transaction_base(self, from_address: str, gas_limit: int = None) -> Dict[str, Any]:
        """Prepare base transaction parameters"""
        return {
            'from': from_address,
            'nonce': self.web3.eth.get_transaction_count(from_address),
            'gas': gas_limit or self.DEFAULT_GAS_LIMIT,
            'gasPrice': self.web3.eth.gas_price
        }
    
    def sign_contract(self, partner_address: str, contract_id: int) -> Dict[str, Any]:
        """Sign a contract on the blockchain with improved validation"""
        self._validate_contract_initialized()
        
        partner_address = self._validate_and_format_address(partner_address, "Partner address")
        tx_params = self._prepare_transaction_base(partner_address)
        
        try:
            tx = self.contract.functions.signContract(contract_id).build_transaction(tx_params)
            return tx
            
        except Exception as e:
            raise ValueError(f"Failed to sign contract: {str(e)}")
    
    def confirm_completion(self, creator_address: str, contract_id: int) -> Dict[str, Any]:
        """Confirm contract completion with improved structure"""
        self._validate_contract_initialized()
        
        creator_address = self._validate_and_format_address(creator_address, "Creator address")
        tx_params = self._prepare_transaction_base(creator_address)
        
        try:
            tx = self.contract.functions.confirmCompletion(contract_id).build_transaction(tx_params)
            return tx
            
        except Exception as e:
            raise ValueError(f"Failed to confirm completion: {str(e)}")
    
    def get_contract_status(self, contract_id: int) -> str:
        """Get contract status with improved error handling"""
        self._validate_contract_initialized()
        
        try:
            status_code = self.contract.functions.getContractStatus(contract_id).call()
            return self.CONTRACT_STATUS_MAP.get(status_code, 'Unknown')
            
        except Exception as e:
            raise ValueError(f"Failed to retrieve contract status: {str(e)}")
    
    def deactivate_contract(self, creator_address: str, contract_id: int) -> Dict[str, Any]:
        """Deactivate contract with improved validation"""
        self._validate_contract_initialized()
        
        creator_address = self._validate_and_format_address(creator_address, "Creator address")
        tx_params = self._prepare_transaction_base(creator_address)
        
        try:
            tx = self.contract.functions.deactivateContract(contract_id).build_transaction(tx_params)
            return tx
            
        except Exception as e:

            raise ValueError(f"Failed to deactivate contract: {str(e)}")
    
    def set_delivery_tracking(self, partner_address: str, contract_id: int, 
                            tracking_number: str) -> Dict[str, Any]:
        """Set delivery tracking with improved structure and validation"""
        self._validate_contract_initialized()
        
        partner_address = self._validate_and_format_address(partner_address, "Partner address")
        
        try:
            # Calculate tracking hash
            tracking_hash = self.calculate_tracking_hash(tracking_number, contract_id)
            tracking_hash_bytes = self._convert_to_bytes32(tracking_hash)
            
            # Prepare transaction
            tx_params = self._prepare_transaction_base(partner_address)
            tx = self.contract.functions.setDeliveryTracking(
                contract_id, 
                tracking_hash_bytes
            ).build_transaction(tx_params)
            
            
            return {
                'success': True,
                'transaction': tx,
                'message': 'Tracking hash prepared for blockchain'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Failed to set delivery tracking: {str(e)}'
            }
    
    def calculate_pdf_hash(self, pdf_file) -> str:
        """Calculate SHA-256 hash with improved error handling"""
        sha256_hash = hashlib.sha256()
        
        try:
            if hasattr(pdf_file, 'read'):
                current_position = getattr(pdf_file, 'tell', lambda: 0)()
                pdf_file.seek(0)
                
                for byte_block in iter(lambda: pdf_file.read(4096), b""):
                    sha256_hash.update(byte_block)
                    
                pdf_file.seek(current_position)
                
            elif isinstance(pdf_file, str) and os.path.exists(pdf_file):
                with open(pdf_file, 'rb') as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
            else:
                raise ValueError("Invalid file input - must be file object or valid file path")
                
            return f'0x{sha256_hash.hexdigest()}'
            
        except Exception as e:
            raise ValueError(f"PDF hash calculation failed: {str(e)}")
    
    def calculate_tracking_hash(self, tracking_number: str, contract_id: int = None) -> bytes:
        """Generate tracking hash with improved validation"""
        if contract_id is None:
            raise ValueError("contract_id is required for tracking hash generation")
        
        # Normalize tracking number
        tracking_number = tracking_number.strip() if tracking_number else ""
        
        if not tracking_number:
            raise ValueError("Tracking number cannot be empty")
        
        try:
            tracking_bytes = tracking_number.encode('utf-8')
            hash_value = self.web3.keccak(tracking_bytes)
            return hash_value
            
        except Exception as e:
            raise ValueError(f"Tracking hash calculation failed: {str(e)}")
    
    def set_contract_address(self, address: str) -> bool:
        """Set contract address with validation"""
        try:
            if self.web3.is_address(address):
                self.contract_address = address
                return self._setup_contract()
            return False
        except Exception as e:
            return False
    
    def get_contract_address(self) -> Optional[str]:
        """Get current contract address"""
        return self.contract_address
    
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