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

/// @title ContractManager - Zentrale Verwaltung digitaler Verträge
/// @notice Dieser Contract speichert Verträge als Datenstrukturen und verwaltet nur Metadaten on‑chain.
contract ContractManager is ReentrancyGuard {
    enum ContractStatus { Created, Signed, Completed, Cancelled }

    struct ManagedContract {
        uint256 id;
        uint256 amount;
        address payable creator;
        address payable counterparty;
        ContractStatus status;
        string contractIPFSHash;
    }

    // Speichert alle Verträge anhand einer eindeutigen ID.
    mapping(uint256 => ManagedContract) public contracts;
    uint256 public contractCounter;

    // Mapping für Guthaben, die von der Gegenpartei abgehoben werden können.
    mapping(address => uint256) public pendingWithdrawals;

    // Events zur Protokollierung wichtiger Aktionen.
    event ContractCreated(uint256 indexed contractId, address creator, address counterparty);
    event ContractSigned(uint256 indexed contractId);
    event PaymentReleased(uint256 indexed contractId, uint256 amount);
    event FundsWithdrawn(address indexed account, uint256 amount);
    event ContractDeactivated(uint256 indexed contractId);

    // Modifier zur Zugriffsbeschränkung.
    modifier onlyCreator(uint256 _contractId) {
        require(msg.sender == contracts[_contractId].creator, "Not creator");
        _;
    }

    modifier onlyCounterparty(uint256 _contractId) {
        require(msg.sender == contracts[_contractId].counterparty, "Not counterparty");
        _;
    }

    /// @notice Erstellt einen neuen Vertrag. Der Ersteller muss den exakten Betrag senden.
    /// @param _counterparty Adresse der Gegenpartei.
    /// @param _contractIPFSHash IPFS-Hash, der auf den Vertragsinhalt verweist.
    /// @param _amount Betrag, der als Sicherheit oder Zahlung hinterlegt wird.
    function createContract(
        address payable _counterparty,
        string memory _contractIPFSHash,
        uint256 _amount
    )
        public
        payable
    {
        require(_counterparty != address(0), "0 addr not allowed");
        require(msg.value == _amount, "ETH mismatch");

        contractCounter++;
        ManagedContract storage newContract = contracts[contractCounter];
        newContract.id = contractCounter;
        newContract.amount = _amount;
        newContract.creator = payable(msg.sender);
        newContract.counterparty = _counterparty;
        newContract.contractIPFSHash = _contractIPFSHash;
        newContract.status = ContractStatus.Created;

        emit ContractCreated(contractCounter, msg.sender, _counterparty);
    }

    /// @notice Die vorgesehene Gegenpartei unterzeichnet den Vertrag.
    /// @param _contractId ID des zu signierenden Vertrags.
    function signContract(uint256 _contractId) public onlyCounterparty(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status == ContractStatus.Created, "Contract not in Created state");

        mContract.status = ContractStatus.Signed;
        emit ContractSigned(_contractId);
    }

    /// @notice Der Ersteller bestätigt die Vertragserfüllung.
    /// Der Betrag wird dabei für eine spätere Auszahlung an die Gegenpartei verbucht.
    /// @param _contractId ID des zu bestätigenden Vertrags.
    function confirmCompletion(uint256 _contractId) public nonReentrant onlyCreator(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status == ContractStatus.Signed, "Contract not signed");

        mContract.status = ContractStatus.Completed;
        pendingWithdrawals[mContract.counterparty] += mContract.amount;
        emit PaymentReleased(_contractId, mContract.amount);
    }

    /// @notice Ermöglicht es Nutzern, ihnen zustehende Gelder abzuheben.
    function withdrawFunds() public nonReentrant {
        uint256 amount = pendingWithdrawals[msg.sender];
        require(amount > 0, "No funds available");

        pendingWithdrawals[msg.sender] = 0;
        (bool success, ) = payable(msg.sender).call{value: amount}("");
        require(success, "Withdrawal failed");
        emit FundsWithdrawn(msg.sender, amount);
    }

    /// @notice Deaktiviert einen Vertrag für DSGVO-Zwecke, indem der off-chain gespeicherte IPFS-Hash gelöscht wird.
    /// Der Vertrag wird als "Cancelled" markiert, sodass keine weiteren Aktionen erfolgen können.
    /// @dev Nur der Ersteller kann diesen Vorgang auslösen. Eine vollständige Löschung der on-chain Daten ist aufgrund der Blockchain-Natur nicht möglich.
    /// @param _contractId ID des zu deaktivierenden Vertrags.
    function deactivateContract(uint256 _contractId) public onlyCreator(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status != ContractStatus.Completed, "Cannot deactivate completed contract");
        require(mContract.status != ContractStatus.Cancelled, "Contract already deactivated");

        // DSGVO-Anforderung: Entfernen des Verweises auf sensible Daten (IPFS-Hash).
        mContract.contractIPFSHash = "";
        mContract.status = ContractStatus.Cancelled;
        emit ContractDeactivated(_contractId);
    }

    /// @notice Gibt den aktuellen Status eines Vertrags zurück.
    /// @param _contractId ID des Vertrags.
    /// @return status Aktueller Status des Vertrags.
    function getContractStatus(uint256 _contractId) public view returns (ContractStatus status) {
        return contracts[_contractId].status;
    }

    /// @notice Gibt den IPFS-Hash eines Vertrags zurück.
    /// @param _contractId ID des Vertrags.
    /// @return hash IPFS-Hash des Vertragsinhalts (kann leer sein, wenn deaktiviert).
    function getContractIPFSHash(uint256 _contractId) public view returns (string memory hash) {
        return contracts[_contractId].contractIPFSHash;
    }
}
