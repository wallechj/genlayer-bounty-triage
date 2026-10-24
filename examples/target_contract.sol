// Demo fixture for BountyTriage. NOT a real project, NOT production code:
// a tiny, simplified DEX pool with one intentional issue, used so that
// Studio triage runs can fetch real target material from a public URL.
// (Raw URL: https://raw.githubusercontent.com/wallechj/genlayer-bounty-triage/main/examples/target_contract.sol)
pragma solidity ^0.8.0;

contract AcmePool {
    address public owner;
    mapping(address => uint256) public pendingFees;

    constructor() {
        owner = msg.sender;
    }

    // Users deposit; a small fee accrues in pendingFees.
    function deposit() external payable {
        pendingFees[msg.sender] += msg.value / 100;
    }

    // INTENTIONAL ISSUE (demo): anyone can call settle() and redirect
    // another user's pending fees to an arbitrary address. There is no
    // onlyOwner / role check here.
    function settle(address user, address to) external {
        uint256 amount = pendingFees[user];
        pendingFees[user] = 0;
        payable(to).transfer(amount);
    }
}
