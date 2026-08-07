# FairnessRegistry Governance Migration Plan

**Status: not executed. This is a plan for a human operator with mainnet deployer access, not
a completed action.** Nothing in this document has been run against Polygon mainnet.

## Why this is a migration, not just a code change

`FairnessRegistry` is already deployed and live on Polygon mainnet:

- Address: `0xc8666f0b9567D447Ce6aaCC1169D15c0E35d0b79` (`FAIRNESS_REGISTRY_ADDRESS` in `.env`)
- Verifier set via `deploy_tx`/`set_verifier_tx` recorded in
  `deployments/polygon_verifier_20260803.json`
- Chain ID 137 (Polygon), policy version `1.3.0` at time of that deployment

`FairnessRegistry.sol` is a plain, non-upgradeable contract - no proxy, no `delegatecall`,
no `Initializable`. Its deployed bytecode is immutable. Adding `transferOwnership()` /
`acceptOwnership()` to the Solidity source (done in this change) has **no effect on the
contract already running on-chain** - that instance was compiled and deployed before this
change existed, and single-EOA ownership (`owner = msg.sender` at construction) cannot be
retrofitted onto it.

The only way to move this system to multisig+timelock governance is to deploy a new
`FairnessRegistry` instance and cut traffic over to it. There is no in-place upgrade path.

## Prerequisites (human operator, not automatable from this repo)

1. A Gnosis Safe, either an existing org Safe or a newly created one, with the intended signer
   set for this responsibility (recommend 2-of-3 minimum, per the original review that flagged
   this single-EOA-ownership finding).
2. The current deployer key (`EVM_PRIVATE_KEY` / whatever now holds `owner` on the live
   contract at `0xc8666f...`) available to sign the cutover transactions.
3. Real POL (Polygon gas token) funded on both the deployer address and, if using a fresh Safe,
   enough for Safe deployment gas.
4. A decision on `minDelay` for the timelock. This plan assumes 48 hours as a starting point -
   long enough to notice and react to a malicious/compromised-signer proposal, short enough to
   not block legitimate operational changes indefinitely. Adjust to your risk tolerance.

## Migration steps

1. **Deploy the new `FairnessRegistry`** with the current `Groth16Verifier` address
   (`0x624331b96A857dfa2e021CD8c149b4813C38dD7C` per the existing deployment record, unless
   also rotating the verifier) as the constructor argument. This uses the same deployer key as
   before; at this point the new contract's `owner` is that EOA, same as the old one was.

2. **Deploy (or reuse) the Gnosis Safe.** If reusing an existing org Safe, confirm its signer
   set and threshold are appropriate for controlling on-chain fairness enforcement specifically,
   not just treasury/other functions.

3. **Deploy a `TimelockController`** (OpenZeppelin, `lib/openzeppelin-contracts` in this repo)
   with:
   - `minDelay`: 48 hours (or your chosen value)
   - `proposers`: `[safeAddress]`
   - `executors`: `[safeAddress]`
   - `admin`: `address(0)` — no single address retains the ability to bypass role
     administration after setup; role changes themselves must go through the timelock.

4. **Transfer ownership of the new registry to the timelock:**
   ```
   newRegistry.transferOwnership(timelockAddress)   // called by the deployer EOA
   ```
   This only sets `pendingOwner` - the registry's `owner` does not change yet.

5. **Accept ownership through the timelock.** The Safe schedules and (after `minDelay`, or
   immediately if you accept a shorter one-time bootstrap delay for this specific action -
   document that exception explicitly if you take it) executes:
   ```
   timelock.schedule(newRegistry, 0, abi.encodeWithSelector(newRegistry.acceptOwnership.selector), ...)
   // wait minDelay
   timelock.execute(newRegistry, 0, abi.encodeWithSelector(newRegistry.acceptOwnership.selector), ...)
   ```
   After this, `newRegistry.owner() == timelockAddress`, and the deployer EOA has no further
   special power over this contract - `setVerifier`/`authorizeSubmitter`/`revokeSubmitter` now
   require a Safe proposal followed by the timelock delay. This is exactly what
   `test/solidity/FairnessRegistryGovernance.t.sol` verifies against the new contract logic.

6. **Authorize the real submitter address(es)** on the new registry via the same
   propose-then-execute path (`authorizeSubmitter`), since a fresh registry starts with only
   the original deployer authorized (from the constructor), not the production bot's signer.

7. **Cut traffic over.** Update `FAIRNESS_REGISTRY_ADDRESS` in:
   - `.env` (and any deployment-specific env files / secret stores mirroring it)
   - `app/core/config.py`'s `fairness_registry_address` default, if hardcoded anywhere outside
     `.env`
   - Any k8s ConfigMap/Secret carrying this value
   Restart/redeploy the services that read this at boot.

8. **Freeze the old contract.** From the old contract's still-EOA owner, call
   `oldRegistry.setPaused(true)` (this function already exists on the deployed contract) to
   signal deprecation and stop new submissions, without needing any code change. Do not attempt
   to reuse the old EOA's ownership powers beyond this - it should not gain the ability to
   authorize new submitters or change the verifier going forward.

9. **Leave the old contract's history intact.** Do not attempt to migrate or delete past
   records - `getRecord()`/`isTransactionProtected()` on the old contract remain valid,
   permanent, publicly verifiable history of what was anchored under the old governance model.
   Anything citing an old `inputCommitment` should keep pointing at the old contract address for
   that historical lookup.

10. **Verify independently before treating the cutover as complete.** Pull up the new
    contract's `owner()` on Polygonscan and confirm it resolves to the `TimelockController`
    address, not an EOA. Confirm the old contract's `paused()` returns `true`. Neither of these
    can be confirmed from this sandbox - do it against the real chain.

## What this repo change does and does not do

- **Does:** add `transferOwnership`/`acceptOwnership` to `FairnessRegistry.sol`, add
  `lib/openzeppelin-contracts` (`TimelockController`) as a dependency, add
  `test/solidity/FairnessRegistryGovernance.t.sol` proving the mechanics work correctly against
  a fresh deployment (single signer cannot call owner functions directly; a queued change cannot
  execute before the delay; it can execute after).
- **Does not:** deploy anything to Polygon mainnet, move the live contract's ownership, or
  change any address referenced in `.env`/k8s config. Those are steps 1-10 above, for a human
  operator to execute deliberately, with real funds and real signing keys.
