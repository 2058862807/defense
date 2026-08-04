// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title UsageAudit
/// @notice On-chain proof-of-usage anchoring for metered pilots. Each audited
/// period's commitment (SHA-256 over usage events + grant balances) is appended
/// as an immutable, queryable record so a credit union / bank / exchange can
/// independently verify how many tokens the pilot actually consumed.
contract UsageAudit {
    address public immutable owner;

    struct PeriodRecord {
        bytes32 commitment;
        uint256 periodStart;
        uint256 eventCount;
        uint256 tokensConsumed;
        uint256 timestamp;
        address recorder;
    }

    mapping(bytes32 => PeriodRecord) public records;
    bytes32[] public commitments;

    event PeriodAnchored(
        bytes32 indexed commitment,
        uint256 periodStart,
        uint256 eventCount,
        uint256 tokensConsumed,
        address recorder,
        uint256 timestamp
    );

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "UsageAudit: not owner");
        _;
    }

    function recordPeriod(
        bytes32 commitment,
        uint256 periodStart,
        uint256 eventCount,
        uint256 tokensConsumed
    ) external onlyOwner {
        require(records[commitment].timestamp == 0, "UsageAudit: duplicate commitment");
        records[commitment] = PeriodRecord({
            commitment: commitment,
            periodStart: periodStart,
            eventCount: eventCount,
            tokensConsumed: tokensConsumed,
            timestamp: block.timestamp,
            recorder: msg.sender
        });
        commitments.push(commitment);
        emit PeriodAnchored(commitment, periodStart, eventCount, tokensConsumed, msg.sender, block.timestamp);
    }

    function getCommitment(bytes32 commitment) external view returns (PeriodRecord memory) {
        return records[commitment];
    }

    function commitmentCount() external view returns (uint256) {
        return commitments.length;
    }
}
