// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {Deploy} from "../script/Deploy.s.sol";

contract DeployTest is Test {
    function test_deploysOnAnvil() public {
        vm.chainId(31337);
        assertTrue(address(new Deploy().run()) != address(0));
    }

    function test_deploysOnRobinhoodTestnet() public {
        vm.chainId(46630);
        assertTrue(address(new Deploy().run()) != address(0));
    }

    function test_refusesMainnetsAndOtherChains() public {
        uint256[3] memory chains = [uint256(1), 4663, 42161]; // Ethereum, Robinhood Chain mainnet, Arbitrum One
        for (uint256 i; i < chains.length; i++) {
            vm.chainId(chains[i]);
            Deploy d = new Deploy();
            vm.expectRevert(abi.encodeWithSelector(Deploy.NotATestnet.selector, chains[i]));
            d.run();
        }
    }
}
