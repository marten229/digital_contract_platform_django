// SPDX-License-Identifier: MIT
pragma solidity ^0.8.21;


/// @dev Minimaler Reentrancy Guard (inspiriert von OpenZeppelin's ReentrancyGuard)
abstract contract ReentrancyGuard {
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;
    
    uint256 private _status;
    
    constructor() {
        _status = _NOT_ENTERED;
    }
    
    modifier nonReentrant() {
        require(_status != _ENTERED, "ReentrancyGuard: reentrant call");
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }
}

contract DigitalContractPlatform is ReentrancyGuard {
    enum ContractStatus { Created, Signed, Completed, Cancelled }

    // Optimierte Reihenfolge zur besseren Speicherpackung:
    struct Contract {
        uint256 id;
        uint256 amount;
        address payable creator;
        address payable counterparty;
        ContractStatus status;
        string contractIPFSHash;
    }

    // Namensparameter für Mappings (Solidity 0.8.18+)
    mapping(uint256 contractId => Contract) public contracts;
    uint256 public contractCounter;

    // Mapping für Guthaben, die von der Gegenpartei abgehoben werden können.
    mapping(address account => uint256) public pendingWithdrawals;

    event ContractCreated(uint256 indexed contractId, address creator, address counterparty);
    event ContractSigned(uint256 indexed contractId);
    event PaymentReleased(uint256 indexed contractId, uint256 amount);
    event FundsWithdrawn(address indexed account, uint256 amount);

    // Modifier zur Zugriffsbeschränkung
    modifier onlyCreator(uint256 _contractId) {
        require(msg.sender == contracts[_contractId].creator, "Not creator");
        _;
    }

    modifier onlyCounterparty(uint256 _contractId) {
        require(msg.sender == contracts[_contractId].counterparty, "Not counterparty");
        _;
    }

    /// @notice Erstelle einen neuen Vertrag. Der Ersteller muss den exakten Betrag senden.
    function createContract(
        address payable _counterparty, 
        string memory _contractIPFSHash, 
        uint256 _amount
    ) 
        public 
        payable 
    {
        require(_counterparty != address(0), "0 addr");
        require(msg.value == _amount, "ETH mismatch");

        contractCounter++;
        // Feld-für-Feld-Zuweisung (günstiger als eine Komplettzuweisung)
        Contract storage newContract = contracts[contractCounter];
        newContract.id = contractCounter;
        newContract.amount = _amount;
        newContract.creator = payable(msg.sender);
        newContract.counterparty = _counterparty;
        newContract.contractIPFSHash = _contractIPFSHash;
        newContract.status = ContractStatus.Created;

        emit ContractCreated(contractCounter, msg.sender, _counterparty);
    }

    /// @notice Die vorgesehene Gegenpartei unterzeichnet den Vertrag.
    function signContract(uint256 _contractId) public onlyCounterparty(_contractId) {
        Contract storage digitalContract = contracts[_contractId];
        require(digitalContract.status == ContractStatus.Created, "Status err");

        digitalContract.status = ContractStatus.Signed;
        emit ContractSigned(_contractId);
    }

    /// @notice Der Ersteller bestätigt die Vertragserfüllung. Der Betrag wird nicht sofort überwiesen,
    /// sondern für eine spätere Abhebung durch die Gegenpartei verbucht.
    function confirmCompletion(uint256 _contractId) public nonReentrant onlyCreator(_contractId) {
        Contract storage digitalContract = contracts[_contractId];
        require(digitalContract.status == ContractStatus.Signed, "Not signed");

        digitalContract.status = ContractStatus.Completed;
        // Nutzung des Addition-Operators statt '+=' zur Gasoptimierung
        pendingWithdrawals[digitalContract.counterparty] = pendingWithdrawals[digitalContract.counterparty] + digitalContract.amount;
        emit PaymentReleased(_contractId, digitalContract.amount);
    }

    /// @notice Ermöglicht es Nutzern, ihnen zustehende Gelder abzuheben.
    function withdrawFunds() public nonReentrant {
        uint256 amount = pendingWithdrawals[msg.sender];
        require(amount != 0, "No funds");

        pendingWithdrawals[msg.sender] = 0;
        (bool success, ) = payable(msg.sender).call{value: amount}("");
        require(success, "Withdraw fail");
        emit FundsWithdrawn(msg.sender, amount);
    }

    /// @notice Gibt den aktuellen Status eines Vertrags zurück.
    function getContractStatus(uint256 _contractId) public view returns (ContractStatus) {
        return contracts[_contractId].status;
    }

    /// @notice Gibt den IPFS-Hash eines Vertrags zurück.
    function getContractIPFSHash(uint256 _contractId) public view returns (string memory) {
        return contracts[_contractId].contractIPFSHash;
    }
}