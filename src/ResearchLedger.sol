// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title ResearchLedger
/// @notice Commit-reveal ledger for research calls. An author commits a hash of a call
///         before the event, then reveals the call and salt afterwards. Anyone can check
///         that the revealed call is exactly what was committed, and when.
/// @dev    Deliberately minimal: no funds, no owner/admin, no upgradeability, no external
///         calls. The commitment binds the author, the chain and this contract, so a hash
///         cannot be copied by another address or replayed on another chain or ledger:
///         keccak256(abi.encode(author, block.chainid, address(this), keccak256(bytes(callJson)), salt))
contract ResearchLedger {
    struct Receipt {
        address author;
        uint64 committedAt; // block timestamp of the commit
        uint64 revealedAt; // block timestamp of the reveal, 0 while locked
        bytes32 commitment;
        bytes32 callHash; // keccak256(bytes(callJson)) once revealed
    }

    Receipt[] private _receipts;
    mapping(bytes32 commitment => bool used) public commitmentUsed;

    event Committed(uint256 indexed id, address indexed author, bytes32 indexed commitment, uint64 committedAt);
    event Revealed(uint256 indexed id, address indexed author, bytes32 callHash, string callJson, bytes32 salt);

    error ZeroCommitment();
    error DuplicateCommitment();
    error UnknownId(uint256 id);
    error NotAuthor();
    error AlreadyRevealed();
    error CommitmentMismatch();

    /// @notice Lock in a call. Only its hash goes on-chain; the call stays private.
    /// @return id Sequential receipt id.
    function commit(bytes32 commitment) external returns (uint256 id) {
        if (commitment == bytes32(0)) revert ZeroCommitment();
        if (commitmentUsed[commitment]) revert DuplicateCommitment();
        commitmentUsed[commitment] = true;
        id = _receipts.length;
        _receipts.push(
            Receipt({
                author: msg.sender,
                committedAt: uint64(block.timestamp),
                revealedAt: 0,
                commitment: commitment,
                callHash: bytes32(0)
            })
        );
        emit Committed(id, msg.sender, commitment, uint64(block.timestamp));
    }

    /// @notice Publish the call and salt. Reverts unless they reproduce the committed hash.
    function reveal(uint256 id, string calldata callJson, bytes32 salt) external {
        if (id >= _receipts.length) revert UnknownId(id);
        Receipt storage r = _receipts[id];
        if (msg.sender != r.author) revert NotAuthor();
        if (r.revealedAt != 0) revert AlreadyRevealed();
        if (commitmentFor(msg.sender, callJson, salt) != r.commitment) revert CommitmentMismatch();
        bytes32 callHash = keccak256(bytes(callJson));
        r.revealedAt = uint64(block.timestamp);
        r.callHash = callHash;
        emit Revealed(id, msg.sender, callHash, callJson, salt);
    }

    /// @notice The commitment an author must submit for a given call and salt on this ledger.
    function commitmentFor(address author, string calldata callJson, bytes32 salt) public view returns (bytes32) {
        return keccak256(abi.encode(author, block.chainid, address(this), keccak256(bytes(callJson)), salt));
    }

    function getReceipt(uint256 id) external view returns (Receipt memory) {
        if (id >= _receipts.length) revert UnknownId(id);
        return _receipts[id];
    }

    function count() external view returns (uint256) {
        return _receipts.length;
    }
}
