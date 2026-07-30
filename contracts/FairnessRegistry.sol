// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * FairnessRegistry - on-chain anchor for ZK XAI fairness proofs
 * Stores commitments + proof verification for offensive and defensive bots
 * Regulatory feedback API can query this for audit
 */

interface IZKVerifier {
    function verifyProof(bytes memory proof, bytes32[] memory publicInputs) external view returns (bool);
}

contract FairnessRegistry {
    struct FairnessRecord {
        bytes32 modelCommitment;
        bytes32 inputCommitment;
        bytes32 proofHash;
        bool isFair;
        bool isOffense;
        string metadata; // JSON with reasons, score, policy
        address submitter;
        uint256 timestamp;
        bool verified;
    }

    mapping(bytes32 => FairnessRecord) public records; // inputCommitment => record
    mapping(address => bool) public authorizedSubmitters;
    IZKVerifier public zkVerifier;

    event FairnessSubmitted(
        bytes32 indexed inputCommitment,
        bytes32 indexed modelCommitment,
        bool isFair,
        bool isOffense,
        address submitter,
        bytes32 proofHash
    );

    event OffenseBlocked(bytes32 indexed inputCommitment, string reason);

    modifier onlyAuthorized() {
        require(authorizedSubmitters[msg.sender] || authorizedSubmitters[address(0)], "Not authorized");
        _;
    }

    constructor(address _verifier) {
        zkVerifier = IZKVerifier(_verifier);
        authorizedSubmitters[msg.sender] = true;
        authorizedSubmitters[address(0)] = true; // open for demo - in prod restrict
    }

    function submitFairnessProof(
        bytes32 modelCommitment,
        bytes32 inputCommitment,
        bytes memory proof,
        bool isFair,
        string memory metadata,
        bool isOffense
    ) external onlyAuthorized {
        // Verify ZK proof if verifier set
        bool verified = true;
        if (address(zkVerifier) != address(0) && proof.length > 0) {
            bytes32[] memory publicInputs = new bytes32[](3);
            publicInputs[0] = modelCommitment;
            publicInputs[1] = inputCommitment;
            publicInputs[2] = isFair ? bytes32(uint256(1)) : bytes32(uint256(0));
            verified = zkVerifier.verifyProof(proof, publicInputs);
            require(verified || !isOffense, "Offense proof must verify");
        }

        // Enforce fairness for offense
        if (isOffense && !isFair) {
            emit OffenseBlocked(inputCommitment, metadata);
            revert("Offensive bundle violates fairness policy");
        }

        records[inputCommitment] = FairnessRecord({
            modelCommitment: modelCommitment,
            inputCommitment: inputCommitment,
            proofHash: keccak256(proof),
            isFair: isFair,
            isOffense: isOffense,
            metadata: metadata,
            submitter: msg.sender,
            timestamp: block.timestamp,
            verified: verified
        });

        emit FairnessSubmitted(inputCommitment, modelCommitment, isFair, isOffense, msg.sender, keccak256(proof));
    }

    function verifyProof(bytes32 inputCommitment) external view returns (bool) {
        return records[inputCommitment].verified;
    }

    function isTransactionProtected(bytes32 inputCommitment) external view returns (bool) {
        FairnessRecord memory r = records[inputCommitment];
        return r.timestamp > 0 && r.isFair && !r.isOffense;
    }

    // Regulatory view
    function getRecord(bytes32 inputCommitment) external view returns (FairnessRecord memory) {
        return records[inputCommitment];
    }
}
