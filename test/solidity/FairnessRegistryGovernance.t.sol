// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {FairnessRegistry} from "../../contracts/FairnessRegistry.sol";
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";

/// @dev Always-true verifier so these tests can focus purely on ownership/
/// timelock governance, not Groth16 proof mechanics (covered elsewhere).
contract MockVerifier {
    function verifyProof(
        uint256[2] calldata,
        uint256[2][2] calldata,
        uint256[2] calldata,
        uint256[3] calldata
    ) external pure returns (bool) {
        return true;
    }
}

/// @dev Simulates "the Safe" as a single address holding both the proposer
/// and executor role on the TimelockController. A real deployment points
/// these roles at an actual Gnosis Safe (M-of-N signature enforcement is
/// Safe's job, already audited there, not re-tested here) - what these
/// tests verify is that FairnessRegistry itself cannot be governed by a bare
/// EOA and cannot be changed faster than the timelock delay, regardless of
/// who holds the proposer/executor role.
contract FairnessRegistryGovernanceTest is Test {
    FairnessRegistry registry;
    TimelockController timelock;
    MockVerifier verifierA;
    MockVerifier verifierB;

    address deployer = address(this);
    address safeSigner = address(0xBEEF);
    address randomEOA = address(0xDEAD);
    uint256 constant MIN_DELAY = 2 days;

    function setUp() public {
        verifierA = new MockVerifier();
        verifierB = new MockVerifier();
        registry = new FairnessRegistry(address(verifierA));

        address[] memory proposers = new address[](1);
        proposers[0] = safeSigner;
        address[] memory executors = new address[](1);
        executors[0] = safeSigner;
        // admin = address(0): no single address can bypass the timelock's
        // own role administration after setup.
        timelock = new TimelockController(MIN_DELAY, proposers, executors, address(0));

        // Two-step handoff: deployer proposes, the timelock contract itself
        // must accept - this is the last action taken directly by the
        // deploying EOA before it has no further special power.
        registry.transferOwnership(address(timelock));

        bytes memory acceptCall = abi.encodeWithSelector(registry.acceptOwnership.selector);
        vm.prank(safeSigner);
        timelock.schedule(address(registry), 0, acceptCall, bytes32(0), bytes32(0), MIN_DELAY);
        skip(MIN_DELAY);
        vm.prank(safeSigner);
        timelock.execute(address(registry), 0, acceptCall, bytes32(0), bytes32(0));

        assertEq(registry.owner(), address(timelock));
    }

    // (a) A single signer cannot execute an owner-only function alone -
    // ownership lives with the timelock contract, not any EOA, so even the
    // address holding both proposer and executor roles cannot call
    // setVerifier/authorizeSubmitter/revokeSubmitter directly.
    function test_singleSignerCannotCallOwnerFunctionDirectly() public {
        vm.prank(safeSigner);
        vm.expectRevert(bytes("Only owner"));
        registry.setVerifier(address(verifierB));

        vm.prank(safeSigner);
        vm.expectRevert(bytes("Only owner"));
        registry.authorizeSubmitter(randomEOA);

        vm.prank(randomEOA);
        vm.expectRevert(bytes("Only owner"));
        registry.revokeSubmitter(safeSigner);
    }

    // (b) A queued change cannot execute before the timelock expires.
    function test_queuedSetVerifierCannotExecuteBeforeDelay() public {
        bytes memory data = abi.encodeWithSelector(registry.setVerifier.selector, address(verifierB));

        vm.prank(safeSigner);
        timelock.schedule(address(registry), 0, data, bytes32(0), bytes32(uint256(1)), MIN_DELAY);

        // Not ready yet - no time has passed.
        vm.prank(safeSigner);
        vm.expectRevert();
        timelock.execute(address(registry), 0, data, bytes32(0), bytes32(uint256(1)));

        // Still not ready with only half the delay elapsed.
        skip(MIN_DELAY / 2);
        vm.prank(safeSigner);
        vm.expectRevert();
        timelock.execute(address(registry), 0, data, bytes32(0), bytes32(uint256(1)));

        assertEq(address(registry.zkVerifier()), address(verifierA), "verifier must be unchanged");
    }

    // (c) It can execute after the delay.
    function test_queuedSetVerifierExecutesAfterDelay() public {
        bytes memory data = abi.encodeWithSelector(registry.setVerifier.selector, address(verifierB));

        vm.prank(safeSigner);
        timelock.schedule(address(registry), 0, data, bytes32(0), bytes32(uint256(2)), MIN_DELAY);

        skip(MIN_DELAY);

        vm.prank(safeSigner);
        timelock.execute(address(registry), 0, data, bytes32(0), bytes32(uint256(2)));

        assertEq(address(registry.zkVerifier()), address(verifierB), "verifier must be updated");
    }

    // Same timelock discipline applies to authorizeSubmitter/revokeSubmitter.
    function test_authorizeSubmitterRespectsTimelock() public {
        bytes memory data = abi.encodeWithSelector(registry.authorizeSubmitter.selector, randomEOA);

        vm.prank(safeSigner);
        timelock.schedule(address(registry), 0, data, bytes32(0), bytes32(uint256(3)), MIN_DELAY);

        vm.prank(safeSigner);
        vm.expectRevert();
        timelock.execute(address(registry), 0, data, bytes32(0), bytes32(uint256(3)));
        assertFalse(registry.authorizedSubmitters(randomEOA));

        skip(MIN_DELAY);
        vm.prank(safeSigner);
        timelock.execute(address(registry), 0, data, bytes32(0), bytes32(uint256(3)));
        assertTrue(registry.authorizedSubmitters(randomEOA));
    }

    function test_revokeSubmitterRespectsTimelock() public {
        // First authorize randomEOA through the timelock so there's something to revoke.
        bytes memory authData = abi.encodeWithSelector(registry.authorizeSubmitter.selector, randomEOA);
        vm.prank(safeSigner);
        timelock.schedule(address(registry), 0, authData, bytes32(0), bytes32(uint256(4)), MIN_DELAY);
        skip(MIN_DELAY);
        vm.prank(safeSigner);
        timelock.execute(address(registry), 0, authData, bytes32(0), bytes32(uint256(4)));
        assertTrue(registry.authorizedSubmitters(randomEOA));

        bytes memory revokeData = abi.encodeWithSelector(registry.revokeSubmitter.selector, randomEOA);
        vm.prank(safeSigner);
        timelock.schedule(address(registry), 0, revokeData, bytes32(0), bytes32(uint256(5)), MIN_DELAY);

        vm.prank(safeSigner);
        vm.expectRevert();
        timelock.execute(address(registry), 0, revokeData, bytes32(0), bytes32(uint256(5)));
        assertTrue(registry.authorizedSubmitters(randomEOA), "must still be authorized before delay elapses");

        skip(MIN_DELAY);
        vm.prank(safeSigner);
        timelock.execute(address(registry), 0, revokeData, bytes32(0), bytes32(uint256(5)));
        assertFalse(registry.authorizedSubmitters(randomEOA));
        assertTrue(registry.revokedSubmitters(randomEOA));
    }

    // transferOwnership itself is two-step and owner-gated.
    function test_pendingOwnerMustAcceptTransfer() public {
        // Nobody but the timelock (current owner) can propose a transfer.
        vm.prank(randomEOA);
        vm.expectRevert(bytes("Only owner"));
        registry.transferOwnership(randomEOA);

        // Simulate the timelock itself proposing a transfer to a new address.
        bytes memory data = abi.encodeWithSelector(registry.transferOwnership.selector, randomEOA);
        vm.prank(safeSigner);
        timelock.schedule(address(registry), 0, data, bytes32(0), bytes32(uint256(6)), MIN_DELAY);
        skip(MIN_DELAY);
        vm.prank(safeSigner);
        timelock.execute(address(registry), 0, data, bytes32(0), bytes32(uint256(6)));

        assertEq(registry.pendingOwner(), randomEOA);
        assertEq(registry.owner(), address(timelock), "ownership must not change until accepted");

        // Only the pending owner can accept.
        vm.prank(safeSigner);
        vm.expectRevert(bytes("Not pending owner"));
        registry.acceptOwnership();

        vm.prank(randomEOA);
        registry.acceptOwnership();
        assertEq(registry.owner(), randomEOA);
    }
}
