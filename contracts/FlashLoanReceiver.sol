// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title FlashLoanReceiver
/// @notice Minimal Aave V3 IFlashLoanSimpleReceiver used by the PROTEAN
///   offense/defense bots to execute zero-capital arbitrage on Polygon.
///   Owner is the bot's EVM signer; only the Aave Pool may call
///   executeOperation. All swaps go through the allowlisted Uniswap V3
///   SwapRouter. Any profit is returned to the owner in the same tx.
interface IFlashLoanSimpleReceiver {
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface ISwapRouter {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }
    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut);
}

contract FlashLoanReceiver is IFlashLoanSimpleReceiver {
    address public immutable owner;
    address public immutable pool;
    address public immutable router;

    constructor(address _pool, address _router) {
        owner = msg.sender;
        pool = _pool;
        router = _router;
    }

    /// @param params abi.encode(address tokenMid, uint24 feeA, uint24 feeB, uint256 amountOutMin)
    ///   swap asset->tokenMid on feeA pool, then tokenMid->asset on feeB pool.
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        require(msg.sender == pool, "only pool");
        require(initiator == owner, "only owner");

        (address tokenMid, uint24 feeA, uint24 feeB, uint256 amountOutMin) =
            abi.decode(params, (address, uint24, uint24, uint256));

        uint256 balanceAsset = IERC20(asset).balanceOf(address(this));
        require(balanceAsset >= amount, "loan not received");

        uint256 repayment = amount + premium;

        uint256 outAsset;
        if (tokenMid == asset) {
            // Pass-through mode: no swaps, just repay. The premium must already
            // be in the contract (owner funds a small buffer). Used for on-chain
            // smoke tests of the flash loan machinery (borrow -> callback -> repay).
            require(balanceAsset >= repayment, "premium buffer insufficient");
            outAsset = amount;
        } else {
            IERC20(asset).approve(router, balanceAsset);
            uint256 midBal = ISwapRouter(router).exactInputSingle(
                ISwapRouter.ExactInputSingleParams({
                    tokenIn: asset,
                    tokenOut: tokenMid,
                    fee: feeA,
                    recipient: address(this),
                    deadline: block.timestamp,
                    amountIn: balanceAsset,
                    amountOutMinimum: 1,
                    sqrtPriceLimitX96: 0
                })
            );

            IERC20(tokenMid).approve(router, midBal);
            outAsset = ISwapRouter(router).exactInputSingle(
                ISwapRouter.ExactInputSingleParams({
                    tokenIn: tokenMid,
                    tokenOut: asset,
                    fee: feeB,
                    recipient: address(this),
                    deadline: block.timestamp,
                    amountIn: midBal,
                    amountOutMinimum: amountOutMin,
                    sqrtPriceLimitX96: 0
                })
            );
            require(outAsset >= repayment, "not repayable");
        }

        IERC20(asset).approve(pool, repayment);
        uint256 profit = outAsset > repayment ? outAsset - repayment : 0;
        if (profit > 0) {
            IERC20(asset).transfer(owner, profit);
        }
        return true;
    }

    function withdraw(address token, uint256) external {
        require(msg.sender == owner, "only owner");
        uint256 bal = IERC20(token).balanceOf(address(this));
        if (bal > 0) {
            IERC20(token).transfer(owner, bal);
        }
    }
}
