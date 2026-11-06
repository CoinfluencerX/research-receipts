// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Script, console2} from "forge-std/Script.sol";
import {ResearchLedger} from "../src/ResearchLedger.sol";

/// @notice Deploys ResearchLedger. TESTNET ONLY: refuses any chain except
///         Robinhood Chain Testnet (46630) and a local anvil (31337).
///         Usage (from your Mac, key from your encrypted Foundry keystore):
///         forge script script/Deploy.s.sol --rpc-url robinhood_testnet --account receipts-testnet --broadcast
contract Deploy is Script {
    uint256 internal constant ROBINHOOD_TESTNET = 46630;
    uint256 internal constant ANVIL = 31337;

    error NotATestnet(uint256 chainId);

    function run() external returns (ResearchLedger ledger) {
        if (block.chainid != ROBINHOOD_TESTNET && block.chainid != ANVIL) revert NotATestnet(block.chainid);
        vm.startBroadcast();
        ledger = new ResearchLedger();
        vm.stopBroadcast();
        console2.log("ResearchLedger deployed at", address(ledger));
        console2.log("chain id", block.chainid);
    }
}
