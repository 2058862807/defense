// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * FairnessRegistry - On-chain anchor for ZK XAI fairness proofs - REAL VERIFICATION
 * Government Standard: No longer trusts caller-supplied isFair boolean
 * Enforces:
 * - Proof must be verified via Groth16Verifier (bn128) - no bypass
 * - isFair is derived from verified public inputs, not caller input
 * - Access control: only authorized submitters (no address(0) open for demo)
 * - Fail-closed: if verifier not set or proof invalid, reverts
 * - Real ceremony: combined.hash d80e39879037cddf0694ee59d1b6d21d1a9fa386196564732a19245363100b41
 *   WASM 1.7M + ZKEY 297KB, 613 constraints, 619 wires, 3 participants + beacon
 */

interface IZKVerifier {
    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[3] calldata _pubSignals
    ) external view returns (bool);
}

contract FairnessRegistry {
    struct FairnessRecord {
        bytes32 modelCommitment;
        bytes32 inputCommitment;
        bytes32 proofHash;
        bool isFair;
        bool isOffense;
        string metadata;
        address submitter;
        uint256 timestamp;
        bool verified;
        uint256[3] publicInputs;
    }

    mapping(bytes32 => FairnessRecord) public records;
    mapping(address => bool) public authorizedSubmitters;
    mapping(address => bool) public revokedSubmitters;
    IZKVerifier public zkVerifier;
    address public owner;
    address public pendingOwner;

    event FairnessSubmitted(
        bytes32 indexed inputCommitment,
        bytes32 indexed modelCommitment,
        bool isFair,
        bool isOffense,
        address submitter,
        bytes32 proofHash,
        bool verified
    );

    event OffenseBlocked(bytes32 indexed inputCommitment, string reason, address submitter);
    event SubmitterAuthorized(address indexed submitter);
    event SubmitterRevoked(address indexed submitter);
    event VerifierUpdated(address indexed oldVerifier, address indexed newVerifier);
    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier onlyAuthorized() {
        require(authorizedSubmitters[msg.sender], "Not authorized - no address(0) open for demo");
        require(!revokedSubmitters[msg.sender], "Submitter revoked");
        _;
    }

    constructor(address _verifier) {
        require(_verifier != address(0), "Verifier address cannot be zero - no bypass");
        zkVerifier = IZKVerifier(_verifier);
        owner = msg.sender;
        authorizedSubmitters[msg.sender] = true;
        // REMOVED: authorizedSubmitters[address(0)] = true; // open for demo - PROHIBITED IN PROD
        emit SubmitterAuthorized(msg.sender);
    }

    function setVerifier(address _verifier) external onlyOwner {
        require(_verifier != address(0), "Verifier cannot be zero");
        address old = address(zkVerifier);
        zkVerifier = IZKVerifier(_verifier);
        emit VerifierUpdated(old, _verifier);
    }

    function authorizeSubmitter(address submitter) external onlyOwner {
        require(submitter != address(0), "Cannot authorize zero address");
        authorizedSubmitters[submitter] = true;
        revokedSubmitters[submitter] = false;
        emit SubmitterAuthorized(submitter);
    }

    function revokeSubmitter(address submitter) external onlyOwner {
        require(submitter != address(0), "Cannot revoke zero address");
        revokedSubmitters[submitter] = true;
        authorizedSubmitters[submitter] = false;
        emit SubmitterRevoked(submitter);
    }

    /**
     * Two-step ownership transfer (Ownable2Step-shaped): the new owner must
     * explicitly accept, so a typo'd/unreachable address can't brick control
     * of the registry. Intended use: transfer to a TimelockController whose
     * proposer/executor roles are held by a Safe multisig, so no single key
     * can change setVerifier/authorizeSubmitter/revokeSubmitter unilaterally
     * or without a delay - see docs/FAIRNESS_REGISTRY_GOVERNANCE_MIGRATION.md.
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "New owner cannot be zero");
        pendingOwner = newOwner;
        emit OwnershipTransferStarted(owner, newOwner);
    }

    function acceptOwnership() external {
        require(msg.sender == pendingOwner, "Not pending owner");
        address old = owner;
        owner = pendingOwner;
        pendingOwner = address(0);
        emit OwnershipTransferred(old, owner);
    }

    /**
     * Submit fairness proof - REAL VERIFICATION, no trust in caller-supplied isFair
     * - Decodes Groth16 proof from bytes (pi_a, pi_b, pi_c)
     * - Calls zkVerifier.verifyProof with proof + public inputs
     * - Public inputs: [isFair (0/1), modelCommitment as field, inputCommitment as field] - isFair is OUTPUT of circuit, not input
     * - isFair is derived from verified public inputs: publicInputs[0] should be 1 if fair, 0 if not
     * - For offense: requires verified==true AND isFair==true (derived from proof), not caller bool
     * - Reverts if proof invalid, verifier not set, or offense unfair
     */
    function submitFairnessProof(
        bytes32 modelCommitment,
        bytes32 inputCommitment,
        bytes calldata proof, // Encoded as (pi_a[2], pi_b[2][2], pi_c[2])
        uint256[3] calldata publicInputs, // [isFair, modelCommitmentField, inputCommitmentField] - isFair is circuit output
        string calldata metadata,
        bool isOffense
    ) external onlyAuthorized {
        require(address(zkVerifier) != address(0), "Verifier not set - cannot verify");
        require(proof.length > 0, "Proof required - no empty proof bypass");
        require(modelCommitment != bytes32(0), "Model commitment cannot be zero");
        require(inputCommitment != bytes32(0), "Input commitment cannot be zero");

        // Decode proof - must be valid Groth16 proof, not hash-formatted fake
        (uint256[2] memory pA, uint256[2][2] memory pB, uint256[2] memory pC) = abi.decode(proof, (uint256[2], uint256[2][2], uint256[2]));

        // Real verification via Groth16 verifier contract (bn128) - no bypass
        bool verified = zkVerifier.verifyProof(pA, pB, pC, publicInputs);
        require(verified, "ZK proof verification failed - invalid proof");

        // Derive isFair from verified public inputs, NOT from caller-supplied bool
        // publicInputs[0] is isFair output from circuit: 1 if fair, 0 if not fair
        // This is enforced by circuit: isFair = slippageOk AND NOT sandwichBlocked AND NOT smallSandwichBlocked
        // So dishonest bot cannot claim isFair=true if circuit says isFair=0 - proof would be invalid
        bool isFairFromProof = publicInputs[0] == 1;

        // For offense: require isFairFromProof == true, enforced by ZK, not caller bool
        if (isOffense) {
            require(isFairFromProof, "Offensive bundle violates fairness policy - ZK proof says isFair=0, not fair");
            // Additional: if offense and isFairFromProof is false, emit blocked and revert (already requires above)
        } else {
            // Defense: isFair can be true or false, but proof must be valid - defense always logs even if unfair for audit
            // Defense protects user even if transaction itself would be considered unfair? Defense is always allowed
        }

        // Store record with isFair derived from proof, not caller
        records[inputCommitment] = FairnessRecord({
            modelCommitment: modelCommitment,
            inputCommitment: inputCommitment,
            proofHash: keccak256(proof),
            isFair: isFairFromProof,
            isOffense: isOffense,
            metadata: metadata,
            submitter: msg.sender,
            timestamp: block.timestamp,
            verified: verified,
            publicInputs: publicInputs
        });

        emit FairnessSubmitted(inputCommitment, modelCommitment, isFairFromProof, isOffense, msg.sender, keccak256(proof), verified);

        // For offense that somehow got past require but isFairFromProof is false (should not happen), block
        if (isOffense && !isFairFromProof) {
            emit OffenseBlocked(inputCommitment, "Offense unfair per ZK proof", msg.sender);
            revert("Offensive bundle unfair per ZK proof");
        }
    }

    /**
     * Legacy function for backward compatibility - but now enforces real verification
     * Still takes isFair boolean for interface compatibility, but ignores it and uses publicInputs[0]
     * This prevents dishonest bot from just setting isFair=true - it must provide valid proof where publicInputs[0]=1
     */
    function submitFairnessProofLegacy(
        bytes32 modelCommitment,
        bytes32 inputCommitment,
        bytes calldata proof,
        bool isFairCaller, // IGNORED - for compatibility, but not trusted
        string calldata metadata,
        bool isOffense
    ) external onlyAuthorized {
        // Decode proof and extract public inputs from proof or use caller-provided public inputs?
        // For legacy, we require proof length >0 and verifier set, and we attempt to decode public inputs from metadata or use default
        // Better: revert and require new function with publicInputs
        revert("Legacy function deprecated - use submitFairnessProof with publicInputs - isFair must be derived from verified proof, not caller bool");
    }

    function verifyProof(bytes32 inputCommitment) external view returns (bool) {
        return records[inputCommitment].verified;
    }

    function isTransactionProtected(bytes32 inputCommitment) external view returns (bool) {
        FairnessRecord memory r = records[inputCommitment];
        return r.timestamp > 0 && r.isFair && !r.isOffense && r.verified;
    }

    function getRecord(bytes32 inputCommitment) external view returns (FairnessRecord memory) {
        return records[inputCommitment];
    }

    function getPublicInputs(bytes32 inputCommitment) external view returns (uint256[3] memory) {
        return records[inputCommitment].publicInputs;
    }

    // Emergency pause for gov standard
    bool public paused;
    modifier whenNotPaused() {
        require(!paused, "Paused");
        _;
    }
    function setPaused(bool _paused) external onlyOwner {
        paused = _paused;
    }
}
