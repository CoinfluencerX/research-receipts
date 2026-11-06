// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {ResearchLedger} from "../src/ResearchLedger.sol";

contract ResearchLedgerTest is Test {
    ResearchLedger internal ledger;
    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");

    string internal constant CALL =
        '{"baseline":"close on horizon_start_date","confidence":0.65,"created_at":"2027-01-20T14:00:00Z","direction":"up","event":"Q4 FY2026 earnings","horizon_end_date":"2027-02-18","horizon_start_date":"2027-02-10","thesis_sha256":"0000000000000000000000000000000000000000000000000000000000000000","ticker":"HOOD","asset_type":"equity"}';
    bytes32 internal constant SALT = keccak256("salt-for-tests-only");

    event Committed(uint256 indexed id, address indexed author, bytes32 indexed commitment, uint64 committedAt);
    event Revealed(uint256 indexed id, address indexed author, bytes32 callHash, string callJson, bytes32 salt);

    function setUp() public {
        ledger = new ResearchLedger();
        vm.warp(1_800_000_000);
    }

    function _commitAs(address who, string memory callJson, bytes32 salt) internal returns (uint256 id, bytes32 c) {
        c = ledger.commitmentFor(who, callJson, salt);
        vm.prank(who);
        id = ledger.commit(c);
    }

    // ---- commitment format ----

    function test_commitmentMatchesSpecFormula() public view {
        bytes32 expected = keccak256(abi.encode(alice, block.chainid, address(ledger), keccak256(bytes(CALL)), SALT));
        assertEq(ledger.commitmentFor(alice, CALL, SALT), expected);
    }

    // ---- commit ----

    function test_commitStoresReceiptAndEmits() public {
        bytes32 c = ledger.commitmentFor(alice, CALL, SALT);
        vm.expectEmit(true, true, true, true);
        emit Committed(0, alice, c, uint64(block.timestamp));
        vm.prank(alice);
        uint256 id = ledger.commit(c);

        assertEq(id, 0);
        assertEq(ledger.count(), 1);
        ResearchLedger.Receipt memory r = ledger.getReceipt(id);
        assertEq(r.author, alice);
        assertEq(r.commitment, c);
        assertEq(r.committedAt, uint64(block.timestamp));
        assertEq(r.revealedAt, 0);
    }

    function test_idsAreSequential() public {
        (uint256 a,) = _commitAs(alice, CALL, SALT);
        (uint256 b,) = _commitAs(bob, CALL, SALT);
        assertEq(a, 0);
        assertEq(b, 1);
    }

    function test_rejectsZeroCommitment() public {
        vm.prank(alice);
        vm.expectRevert(ResearchLedger.ZeroCommitment.selector);
        ledger.commit(bytes32(0));
    }

    function test_rejectsDuplicateCommitment() public {
        _commitAs(alice, CALL, SALT);
        bytes32 c = ledger.commitmentFor(alice, CALL, SALT);
        vm.prank(alice);
        vm.expectRevert(ResearchLedger.DuplicateCommitment.selector);
        ledger.commit(c);
    }

    // ---- reveal ----

    function test_revealVerifiesAndEmits() public {
        (uint256 id,) = _commitAs(alice, CALL, SALT);
        vm.warp(block.timestamp + 30 days);
        vm.expectEmit(true, true, false, true);
        emit Revealed(id, alice, keccak256(bytes(CALL)), CALL, SALT);
        vm.prank(alice);
        ledger.reveal(id, CALL, SALT);

        ResearchLedger.Receipt memory r = ledger.getReceipt(id);
        assertEq(r.revealedAt, uint64(block.timestamp));
        assertEq(r.callHash, keccak256(bytes(CALL)));
    }

    function test_revealRejectsWrongSalt() public {
        (uint256 id,) = _commitAs(alice, CALL, SALT);
        vm.prank(alice);
        vm.expectRevert(ResearchLedger.CommitmentMismatch.selector);
        ledger.reveal(id, CALL, bytes32(uint256(SALT) ^ 1));
    }

    function test_revealRejectsTamperedJson() public {
        (uint256 id,) = _commitAs(alice, CALL, SALT);
        string memory tampered = string.concat(CALL, " ");
        vm.prank(alice);
        vm.expectRevert(ResearchLedger.CommitmentMismatch.selector);
        ledger.reveal(id, tampered, SALT);
    }

    function test_onlyAuthorCanReveal() public {
        (uint256 id,) = _commitAs(alice, CALL, SALT);
        vm.prank(bob);
        vm.expectRevert(ResearchLedger.NotAuthor.selector);
        ledger.reveal(id, CALL, SALT);
    }

    function test_noDoubleReveal() public {
        (uint256 id,) = _commitAs(alice, CALL, SALT);
        vm.startPrank(alice);
        ledger.reveal(id, CALL, SALT);
        vm.expectRevert(ResearchLedger.AlreadyRevealed.selector);
        ledger.reveal(id, CALL, SALT);
        vm.stopPrank();
    }

    function test_unknownIdReverts() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(ResearchLedger.UnknownId.selector, 7));
        ledger.reveal(7, CALL, SALT);
        vm.expectRevert(abi.encodeWithSelector(ResearchLedger.UnknownId.selector, 7));
        ledger.getReceipt(7);
    }

    // ---- replay / copy protection ----

    function test_copiedCommitmentCannotBeRevealedByAnotherAuthor() public {
        // Bob sees Alice's commitment in the mempool and submits the same hash as his own.
        bytes32 aliceC = ledger.commitmentFor(alice, CALL, SALT);
        vm.prank(bob);
        uint256 bobId = ledger.commit(aliceC);
        // Even after Alice reveals publicly, Bob cannot reveal "his" receipt: the hash binds Alice's address.
        bytes32 aliceRealC = ledger.commitmentFor(alice, CALL, bytes32(uint256(SALT) + 1));
        vm.prank(alice);
        uint256 aliceId = ledger.commit(aliceRealC);
        vm.prank(alice);
        ledger.reveal(aliceId, CALL, bytes32(uint256(SALT) + 1));
        vm.prank(bob);
        vm.expectRevert(ResearchLedger.CommitmentMismatch.selector);
        ledger.reveal(bobId, CALL, SALT);
    }

    function test_commitmentFromAnotherChainDoesNotVerify() public {
        uint256 originalChain = block.chainid;
        vm.chainId(1);
        bytes32 foreign = keccak256(abi.encode(alice, block.chainid, address(ledger), keccak256(bytes(CALL)), SALT));
        vm.chainId(originalChain);
        vm.prank(alice);
        uint256 id = ledger.commit(foreign);
        vm.prank(alice);
        vm.expectRevert(ResearchLedger.CommitmentMismatch.selector);
        ledger.reveal(id, CALL, SALT);
    }

    function test_commitmentForAnotherLedgerDoesNotVerify() public {
        ResearchLedger other = new ResearchLedger();
        bytes32 forOther = other.commitmentFor(alice, CALL, SALT);
        vm.prank(alice);
        uint256 id = ledger.commit(forOther);
        vm.prank(alice);
        vm.expectRevert(ResearchLedger.CommitmentMismatch.selector);
        ledger.reveal(id, CALL, SALT);
    }

    function test_contractHoldsNoEther() public {
        vm.deal(alice, 1 ether);
        vm.prank(alice);
        (bool ok,) = address(ledger).call{value: 1 wei}("");
        assertFalse(ok);
        assertEq(address(ledger).balance, 0);
    }

    // ---- fuzz ----

    function testFuzz_roundTrip(address author, string calldata callJson, bytes32 salt) public {
        vm.assume(author != address(0));
        bytes32 c = ledger.commitmentFor(author, callJson, salt);
        vm.prank(author);
        uint256 id = ledger.commit(c);
        vm.prank(author);
        ledger.reveal(id, callJson, salt);
        assertEq(ledger.getReceipt(id).callHash, keccak256(bytes(callJson)));
    }

    function testFuzz_wrongSaltNeverVerifies(bytes32 salt, bytes32 wrongSalt) public {
        vm.assume(salt != wrongSalt);
        (uint256 id,) = _commitAs(alice, CALL, salt);
        vm.prank(alice);
        vm.expectRevert(ResearchLedger.CommitmentMismatch.selector);
        ledger.reveal(id, CALL, wrongSalt);
    }

    function testFuzz_wrongAuthorNeverReveals(address other) public {
        vm.assume(other != alice);
        (uint256 id,) = _commitAs(alice, CALL, SALT);
        vm.prank(other);
        vm.expectRevert(ResearchLedger.NotAuthor.selector);
        ledger.reveal(id, CALL, SALT);
    }

    function testFuzz_tamperedJsonNeverVerifies(string calldata original, string calldata tampered) public {
        vm.assume(keccak256(bytes(original)) != keccak256(bytes(tampered)));
        (uint256 id,) = _commitAs(alice, original, SALT);
        vm.prank(alice);
        vm.expectRevert(ResearchLedger.CommitmentMismatch.selector);
        ledger.reveal(id, tampered, SALT);
    }

    function testFuzz_otherChainNeverVerifies(uint64 otherChain) public {
        vm.assume(otherChain != block.chainid && otherChain != 0);
        bytes32 foreign =
            keccak256(abi.encode(alice, uint256(otherChain), address(ledger), keccak256(bytes(CALL)), SALT));
        vm.prank(alice);
        uint256 id = ledger.commit(foreign);
        vm.prank(alice);
        vm.expectRevert(ResearchLedger.CommitmentMismatch.selector);
        ledger.reveal(id, CALL, SALT);
    }
}
