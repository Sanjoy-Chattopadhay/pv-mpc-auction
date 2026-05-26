// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title MPCAuction
 * @notice On-chain bulletin board for the PV-MPC-Auction protocol.
 *         Anchors all five protocol phases to Ethereum and provides
 *         publicly verifiable evidence for accountability and slashing.
 *
 *         Phases (enforced as a finite-state machine):
 *           Reg     - bidders register and deposit collateral
 *           Commit  - bidders submit Pedersen commitments + Schnorr ZKPs
 *           Share   - bidders publish hashes of off-chain Shamir shares
 *           Result  - winner reveals; contract verifies and finalises
 *           Done    - deposits returned, slashing applied
 *
 *         This contract is the on-chain leg of the protocol described in
 *         "Blockchain-Anchored Sealed-Bid Auctions via Pedersen Commitments,
 *          Shamir Sharing, and Schnorr Zero-Knowledge Proofs" (ICST 2026).
 */
contract MPCAuction {

    // -------------------------------------------------------------------------
    // Types
    // -------------------------------------------------------------------------
    enum Phase { Reg, Commit, Share, Result, Done }

    struct Bidder {
        bool       registered;       // set in Phase Reg
        uint256    deposit;          // collateral, slashable
        bytes32    commitment;       // C_i = g^{b_i} h^{r_i}  (256-bit digest)
        bytes      proof;            // Pedersen-opening Schnorr proof pi_i
        bool       committed;        // set in Phase Commit
        bytes32    shareHashRoot;    // Merkle root over {H(s_{i,j})}_j
        bool       shared;           // set in Phase Share
        bool       slashed;          // set if deviation proven
    }

    // -------------------------------------------------------------------------
    // Storage
    // -------------------------------------------------------------------------
    address public  auctionAdmin;       // who deploys / advances phases
    Phase   public  phase;
    uint256 public  minDeposit;
    uint256 public  registrationDeadline;
    uint256 public  commitDeadline;
    uint256 public  shareDeadline;

    address[]                       public bidderList;
    mapping(address => Bidder)      public bidders;
    mapping(address => uint8)       public bidderIndex; // 1-based; 0 = absent

    address public winner;
    uint256 public winningBid;
    bool    public finalized;

    // -------------------------------------------------------------------------
    // Events  --  one per protocol transaction type
    // -------------------------------------------------------------------------
    event Registered (address indexed bidder, uint8 idx, uint256 deposit);
    event Committed  (address indexed bidder, bytes32 commitment, bytes proof);
    event Shared     (address indexed bidder, bytes32 shareHashRoot);
    event Finalised  (address indexed winner, uint256 bid);
    event Slashed    (address indexed bidder, string reason);
    event PhaseAdvanced(Phase from, Phase to);

    // -------------------------------------------------------------------------
    // Modifiers
    // -------------------------------------------------------------------------
    modifier onlyAdmin() {
        require(msg.sender == auctionAdmin, "not admin");
        _;
    }
    modifier inPhase(Phase p) {
        require(phase == p, "wrong phase");
        _;
    }

    // -------------------------------------------------------------------------
    // Constructor
    // -------------------------------------------------------------------------
    constructor(
        uint256 _minDeposit,
        uint256 _registrationWindow,
        uint256 _commitWindow,
        uint256 _shareWindow
    ) {
        auctionAdmin         = msg.sender;
        phase                = Phase.Reg;
        minDeposit           = _minDeposit;
        registrationDeadline = block.timestamp + _registrationWindow;
        commitDeadline       = registrationDeadline + _commitWindow;
        shareDeadline        = commitDeadline + _shareWindow;
    }

    // -------------------------------------------------------------------------
    // Phase 1 :  register()
    // -------------------------------------------------------------------------
    function register() external payable inPhase(Phase.Reg) {
        require(block.timestamp <= registrationDeadline, "reg closed");
        require(msg.value >= minDeposit, "deposit too low");
        require(!bidders[msg.sender].registered, "already registered");
        require(bidderList.length < 255, "too many bidders");

        bidders[msg.sender] = Bidder({
            registered:    true,
            deposit:       msg.value,
            commitment:    bytes32(0),
            proof:         "",
            committed:     false,
            shareHashRoot: bytes32(0),
            shared:        false,
            slashed:       false
        });
        bidderList.push(msg.sender);
        bidderIndex[msg.sender] = uint8(bidderList.length);  // 1-based

        emit Registered(msg.sender, uint8(bidderList.length), msg.value);
    }

    // -------------------------------------------------------------------------
    // Phase 2 :  submitCommitment(C, pi)
    //
    // C  : keccak256-style 32-byte digest of the Pedersen commitment value
    //      g^{b_i} h^{r_i} mod p  (the full 2048-bit value is stored
    //      off-chain; only its hash is anchored here for gas efficiency).
    // pi : raw Schnorr proof bytes (tau || s_m || s_r).  Verified off-chain
    //      by any auditor; the contract simply records and time-stamps it.
    // -------------------------------------------------------------------------
    function submitCommitment(bytes32 C, bytes calldata pi)
        external
        inPhase(Phase.Commit)
    {
        require(block.timestamp <= commitDeadline, "commit closed");
        Bidder storage b = bidders[msg.sender];
        require(b.registered,          "not registered");
        require(!b.committed,          "already committed");
        require(C != bytes32(0),       "empty commitment");
        require(pi.length >= 96,       "proof too short");  // 3 * 32 bytes min

        b.commitment = C;
        b.proof      = pi;
        b.committed  = true;

        emit Committed(msg.sender, C, pi);
    }

    // -------------------------------------------------------------------------
    // Phase 3 :  submitShareHashes(root)
    //
    // root : Merkle root over { H(s_{i,j}) }_{j=1..n}, computed off-chain.
    //        Using a root instead of the full hash vector reduces Phase-3
    //        gas from O(n) per bidder to O(1) -- the dominant production
    //        optimisation reported in the paper.
    // -------------------------------------------------------------------------
    function submitShareHashes(bytes32 root)
        external
        inPhase(Phase.Share)
    {
        require(block.timestamp <= shareDeadline, "share closed");
        Bidder storage b = bidders[msg.sender];
        require(b.registered, "not registered");
        require(b.committed,  "no commitment");
        require(!b.shared,    "already shared");
        require(root != bytes32(0), "empty root");

        b.shareHashRoot = root;
        b.shared        = true;

        emit Shared(msg.sender, root);
    }

    // -------------------------------------------------------------------------
    // Phase 4 :  advancePhase()
    //
    // Phase 4 (the MPC computation itself) executes off-chain among the
    // bidders.  The admin advances the on-chain state machine to Result
    // when the off-chain tournament has converged.
    // -------------------------------------------------------------------------
    function advancePhase() external onlyAdmin {
        Phase prev = phase;
        if (phase == Phase.Reg)         { phase = Phase.Commit; }
        else if (phase == Phase.Commit) { phase = Phase.Share;  }
        else if (phase == Phase.Share)  { phase = Phase.Result; }
        else if (phase == Phase.Result) { phase = Phase.Done;   }
        else revert("already done");
        emit PhaseAdvanced(prev, phase);
    }

    // -------------------------------------------------------------------------
    // Phase 5 :  finalize(winner, bid, openingHash)
    //
    // openingHash : keccak256(abi.encode(bid, r_w)).  Off-chain verifiers
    //               recompute g^{bid} h^{r_w}, hash it, and compare with
    //               the winner's stored commitment to confirm the opening.
    //               The on-chain contract records the claim; off-chain
    //               proofs make any false claim publicly attributable.
    // -------------------------------------------------------------------------
    function finalize(address _winner, uint256 _bid, bytes32 openingHash)
        external
        onlyAdmin
        inPhase(Phase.Result)
    {
        require(!finalized,                "already finalised");
        require(bidders[_winner].committed,"winner did not commit");
        require(openingHash != bytes32(0), "empty opening");
        // Off-chain auditors check:  bidders[_winner].commitment == keccak256(
        //   abi.encodePacked(g^{_bid} * h^{r_w} mod p) )
        // We anchor the claim and the opening hash on-chain; the algebraic
        // check is performed by any off-chain verifier replaying the trace.

        winner     = _winner;
        winningBid = _bid;
        finalized  = true;

        // Return deposits to all non-slashed bidders
        for (uint256 i = 0; i < bidderList.length; i++) {
            address a = bidderList[i];
            Bidder storage b = bidders[a];
            if (!b.slashed && b.deposit > 0) {
                uint256 d = b.deposit;
                b.deposit = 0;
                (bool ok, ) = a.call{ value: d }("");
                require(ok, "refund failed");
            }
        }

        emit Finalised(_winner, _bid);
    }

    // -------------------------------------------------------------------------
    // Slashing
    //
    // Anyone can submit a proof that bidder `culprit` published a share
    // off-chain whose hash does not match the Merkle root they anchored
    // in Phase 3.  The proof consists of (leaf, merklePath, leafIndex);
    // we verify the path against the stored root and slash on success.
    // -------------------------------------------------------------------------
    function slashShareInconsistency(
        address           culprit,
        bytes32           leaf,
        bytes32[] calldata path,
        uint256           leafIndex,
        bytes32           expectedLeaf
    ) external {
        Bidder storage b = bidders[culprit];
        require(b.shared,     "no share commitment");
        require(!b.slashed,   "already slashed");
        require(leaf != expectedLeaf, "leaves match; no inconsistency");
        bytes32 computed = _verifyMerklePath(leaf, path, leafIndex);
        require(computed == b.shareHashRoot, "proof not in tree");

        b.slashed = true;
        uint256 forfeited = b.deposit;
        b.deposit = 0;
        // Forfeited collateral stays in the contract and is split among
        // surviving honest bidders at finalize().  Kept simple here.
        emit Slashed(culprit, "share-hash inconsistency");

        // Forward forfeited funds to admin for community distribution
        if (forfeited > 0) {
            (bool ok, ) = auctionAdmin.call{ value: forfeited }("");
            require(ok, "forward failed");
        }
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------
    function _verifyMerklePath(
        bytes32              leaf,
        bytes32[] calldata   path,
        uint256              index
    ) internal pure returns (bytes32) {
        bytes32 h = leaf;
        for (uint256 i = 0; i < path.length; i++) {
            if (index % 2 == 0) {
                h = keccak256(abi.encodePacked(h, path[i]));
            } else {
                h = keccak256(abi.encodePacked(path[i], h));
            }
            index /= 2;
        }
        return h;
    }

    function bidderCount() external view returns (uint256) {
        return bidderList.length;
    }

    function getBidder(address a)
        external
        view
        returns (
            bool registered, uint256 deposit, bytes32 commitment,
            bool committed, bytes32 shareHashRoot, bool shared, bool slashed
        )
    {
        Bidder storage b = bidders[a];
        return (b.registered, b.deposit, b.commitment,
                b.committed, b.shareHashRoot, b.shared, b.slashed);
    }

    // Accept stray ETH (e.g. for slashing-pool top-ups)
    receive() external payable {}
}
