// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract ContractManager is ReentrancyGuard {
    enum ContractStatus {
        Created,
        Signed,
        DeliverySet,
        DeliveryConfirmed,
        DeliveryApproved,
        AgreementFulfilled,
        Completed,
        Cancelled
    }

    struct ManagedContract {
        uint256 id;
        uint256 amount;
        address payable creator;
        address payable counterparty;
        ContractStatus status;
        bytes32 contractHash;
        bytes32 deliveryTrackingHash;
        bool deliveryRequired;
    }

    address public oracle;
    bool public oracleSet;

    mapping(uint256 => ManagedContract) public contracts;
    uint256 public contractCounter;

    mapping(address => uint256 amount) public pendingWithdrawals;

    event ContractCreated(uint256 indexed contractId, address creator, address counterparty);
    event ContractSigned(uint256 indexed contractId);
    event TrackingHashSet(uint256 indexed contractId, bytes32 trackingHash);
    event DeliveryConfirmed(uint256 indexed contractId);
    event DeliveryApproved(uint256 indexed contractId);
    event PaymentReleased(uint256 indexed contractId, address indexed to, uint256 amount);
    event FundsWithdrawn(uint256 indexed contractId, address indexed account, uint256 amount);
    event ContractDeactivated(uint256 indexed contractId);
    event OracleSet(address indexed oracle);

    modifier onlyCreator(uint256 _contractId) {
        require(msg.sender == contracts[_contractId].creator, "Not creator");
        _;
    }

    modifier onlyCounterparty(uint256 _contractId) {
        require(msg.sender == contracts[_contractId].counterparty, "Not counterparty");
        _;
    }

    modifier onlyOracle() {
        require(msg.sender == oracle, "Not oracle");
        _;
    }

    function setOracle(address _oracle) public {
        require(!oracleSet, "Oracle already set");
        require(_oracle != address(0), "Invalid oracle");

        oracle = _oracle;
        oracleSet = true;
        emit OracleSet(_oracle);
    }

    function createContract(
        address payable _counterparty,
        bytes32 _contractHash,
        uint256 _amount
    ) public payable {
        require(_counterparty != address(0), "0 addr not allowed");
        require(msg.value == _amount, "ETH mismatch");

        contractCounter++;
        ManagedContract storage newContract = contracts[contractCounter];
        newContract.id = contractCounter;
        newContract.amount = _amount;
        newContract.creator = payable(msg.sender);
        newContract.counterparty = _counterparty;
        newContract.status = ContractStatus.Created;
        newContract.contractHash = _contractHash;

        emit ContractCreated(contractCounter, msg.sender, _counterparty);
    }

    function signContract(uint256 _contractId) public onlyCounterparty(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status == ContractStatus.Created, "Not Created");

        mContract.status = ContractStatus.Signed;
        emit ContractSigned(_contractId);
    }

    function setDeliveryTracking(uint256 _contractId, bytes32 _trackingNumberHash) public onlyCounterparty(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status == ContractStatus.Signed, "Not Signed");
        require(!mContract.deliveryRequired, "Already set");

        mContract.deliveryTrackingHash = _trackingNumberHash;
        mContract.deliveryRequired = true;
        mContract.status = ContractStatus.DeliverySet;

        emit TrackingHashSet(_contractId, mContract.deliveryTrackingHash);
    }

    function confirmDeliveryByOracle(uint256 _contractId, bytes32 _trackingNumberHash) public onlyOracle {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status == ContractStatus.DeliverySet, "Wrong status");
        require(mContract.deliveryRequired, "No delivery");

        require(
            mContract.deliveryTrackingHash == _trackingNumberHash,
            "Hash mismatch"
        );

        mContract.status = ContractStatus.DeliveryConfirmed;
        emit DeliveryConfirmed(_contractId);
    }

    function approveDeliveryAsCreator(uint256 _contractId) public onlyCreator(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status == ContractStatus.DeliveryConfirmed, "Wrong status");

        mContract.status = ContractStatus.DeliveryApproved;
        pendingWithdrawals[mContract.counterparty] = pendingWithdrawals[mContract.counterparty] + mContract.amount;

        emit DeliveryApproved(_contractId);
        emit PaymentReleased(_contractId, mContract.counterparty, mContract.amount);
    }

    function confirmCompletion(uint256 _contractId) public onlyCreator(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status == ContractStatus.Signed, "Not signed");
        require(!mContract.deliveryRequired, "Delivery flow required");

        mContract.status = ContractStatus.AgreementFulfilled;
        pendingWithdrawals[mContract.counterparty] = pendingWithdrawals[mContract.counterparty] + mContract.amount;

        emit PaymentReleased(_contractId, mContract.counterparty, mContract.amount);
    }

    function withdrawFundsFrom(uint256 _contractId) public nonReentrant onlyCounterparty(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(
            mContract.status == ContractStatus.AgreementFulfilled ||
            mContract.status == ContractStatus.DeliveryApproved,
            "Not withdrawable"
        );

        uint256 amount = mContract.amount;
        require(pendingWithdrawals[msg.sender] >= amount, "No balance");

        pendingWithdrawals[msg.sender] = pendingWithdrawals[msg.sender] - amount;

        mContract.status = ContractStatus.Completed;

        payable(msg.sender).transfer(amount);

        emit FundsWithdrawn(_contractId, msg.sender, amount);
    }

    function deactivateContract(uint256 _contractId) public onlyCreator(_contractId) {
        ManagedContract storage mContract = contracts[_contractId];
        require(mContract.status == ContractStatus.Completed, "Only Completed");

        delete mContract.contractHash;
        delete mContract.deliveryTrackingHash;
        mContract.status = ContractStatus.Cancelled;

        emit ContractDeactivated(_contractId);
    }

    function getContractStatus(uint256 _contractId) public view returns (ContractStatus) {
        return contracts[_contractId].status;
    }
}
