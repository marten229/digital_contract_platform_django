// SPDX-License-Identifier: MIT
pragma solidity 0.8.21; 

abstract contract ReentrancyGuard {
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;
    
    uint256 private _status;
    
    constructor() {
        _status = _NOT_ENTERED;
    }
    
    modifier nonReentrant() {
        require(_status != _ENTERED, "Reentrant call");
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }
}

contract ContractManager is ReentrancyGuard {
    enum ContractStatus { Created, Signed, Completed, Cancelled }

    struct ManagedContract {
        uint256 id;
        uint256 amount;
        address payable creator;
        address payable counterparty;
        ContractStatus status;
        string contractIPFSHash;
        bytes32 deliveryTrackingHash;
        bool deliveryRequired;
        bool deliveryConfirmed;
        bool deliveryApprovedByCreator;
    }

    mapping(uint256 => ManagedContract) public contracts;
    uint256 public contractCounter;

    mapping(address => uint256) public pendingWithdrawals;

    event ContractCreated(uint256 indexed contractId, address creator, address counterparty);
    event ContractSigned(uint256 indexed contractId);
    event TrackingHashSet(uint256 indexed contractId, bytes32 trackingHash);
    event DeliveryConfirmed(uint256 indexed contractId);
    event DeliveryApproved(uint256 indexed contractId);
    event PaymentReleased(uint256 indexed contractId, uint256 amount);
    event FundsWithdrawn(address indexed account, uint256 amount);
    event ContractDeactivated(uint256 indexed contractId);

    modifier onlyCreator(uint256 _contractId) {
        require(msg.sender == contracts[_contractId].creator, "Not creator");
        _;
    }

    modifier onlyCounterparty(uint256 _contractId) {
        require(msg.sender == contracts[_contractId].counterparty, "Not counterparty");
        _;
    }

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
        contracts[contractCounter] = ManagedContract({
            id: contractCounter,
            amount: _amount,
            creator: payable(msg.sender),
            counterparty: _counterparty,
            status: ContractStatus.Created,
            contractIPFSHash: _contractIPFSHash,
            deliveryTrackingHash: 0,
            deliveryRequired: false,
            deliveryConfirmed: false,
            deliveryApprovedByCreator: false
        });

        emit ContractCreated(contractCounter, msg.sender, _counterparty);
    }

    function signContract(uint256 _contractId) public onlyCounterparty(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status == ContractStatus.Created, "Not Created");

        mContract.status = ContractStatus.Signed;
        emit ContractSigned(_contractId);
    }

    function setDeliveryTracking(uint256 _contractId, string memory _trackingNumber) public onlyCounterparty(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status == ContractStatus.Signed, "Not Signed");
        require(!mContract.deliveryRequired, "Already set");

        mContract.deliveryTrackingHash = keccak256(abi.encode(_trackingNumber));
        mContract.deliveryRequired = true;

        emit TrackingHashSet(_contractId, mContract.deliveryTrackingHash);
    }

    function confirmDeliveryByOracle(uint256 _contractId, string memory _trackingNumber) public nonReentrant {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.deliveryRequired, "No delivery");
        require(mContract.status == ContractStatus.Signed, "Not Signed");
        require(!mContract.deliveryConfirmed, "Already confirmed");

        require(
            mContract.deliveryTrackingHash == keccak256(abi.encode(_trackingNumber)),
            "Hash mismatch"
        );

        mContract.deliveryConfirmed = true;
        emit DeliveryConfirmed(_contractId);
    }

    function approveDeliveryAsCreator(uint256 _contractId) public onlyCreator(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.deliveryRequired, "No delivery");
        require(mContract.status == ContractStatus.Signed, "Not Signed");
        require(mContract.deliveryConfirmed, "Delivery missing");
        require(!mContract.deliveryApprovedByCreator, "Already approved");

        mContract.deliveryApprovedByCreator = true;
        mContract.status = ContractStatus.Completed;
        pendingWithdrawals[mContract.counterparty] = pendingWithdrawals[mContract.counterparty] + mContract.amount;

        emit DeliveryApproved(_contractId);
        emit PaymentReleased(_contractId, mContract.amount);
    }

    function confirmCompletion(uint256 _contractId) public nonReentrant onlyCreator(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status == ContractStatus.Signed, "Not Signed");
        require(!mContract.deliveryRequired, "Use delivery flow");

        mContract.status = ContractStatus.Completed;
        pendingWithdrawals[mContract.counterparty] = pendingWithdrawals[mContract.counterparty] + mContract.amount;

        emit PaymentReleased(_contractId, mContract.amount);
    }

    function withdrawFunds() public nonReentrant {
        uint256 amount = pendingWithdrawals[msg.sender];
        require(amount != 0, "No funds");

        delete pendingWithdrawals[msg.sender];
        (bool success, ) = payable(msg.sender).call{value: amount}("");
        require(success, "Withdraw failed");

        emit FundsWithdrawn(msg.sender, amount);
    }

    function deactivateContract(uint256 _contractId) public onlyCreator(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status != ContractStatus.Completed, "Already completed");
        require(mContract.status != ContractStatus.Cancelled, "Already cancelled");

        mContract.contractIPFSHash = "";
        mContract.status = ContractStatus.Cancelled;

        emit ContractDeactivated(_contractId);
    }

    function getContractStatus(uint256 _contractId) public view returns (ContractStatus) {
        return contracts[_contractId].status;
    }

    function getContractIPFSHash(uint256 _contractId) public view returns (string memory) {
        return contracts[_contractId].contractIPFSHash;
    }
}
