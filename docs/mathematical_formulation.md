# Mathematical Formulation & Microstructure Foundations

## 1. Introduction: What is Order Flow Imbalance (OFI)?

In financial market microstructure, price formation is driven by the dynamic interaction between resting liquidity (limit orders) and aggressive liquidity consumption (market orders).

While traditional quantitative models often rely on low-frequency bar data (OHLCV) or static Order Book Imbalance (OBI), **Rama Cont, Arseniy Kukanov, and Sasha Stoikov (2014)** introduced **Order Flow Imbalance (OFI)** as a dynamic measure of the net order flow driving price changes.

Unlike static depth ratios, OFI accounts for the **exact nature of every order book event**:
- New limit order placements (liquidity additions)
- Limit order cancellations (liquidity withdrawals)
- Market order executions (liquidity consumption)

---

## 2. Cont, Kukanov & Stoikov (2014) Formulation

Let the state of the Limit Order Book (LOB) at discrete event time $t$ be described by:
- $P_b(t)$: Best bid price
- $q_b(t)$: Best bid quantity (available depth at $P_b(t)$)
- $P_a(t)$: Best ask price
- $q_a(t)$: Best ask quantity (available depth at $P_a(t)$)

### 2.1 Bid-Side Order Flow $e_b(t)$

Between consecutive order book states $t-1$ and $t$:

$$
e_b(t) = \begin{cases}
q_b(t), & \text{if } P_b(t) > P_b(t-1) \quad \text{(Price increased: entire new level is fresh demand)} \\
q_b(t) - q_b(t-1), & \text{if } P_b(t) = P_b(t-1) \quad \text{(Price unchanged: net change in resting size)} \\
-q_b(t-1), & \text{if } P_b(t) < P_b(t-1) \quad \text{(Price decreased: previous best bid consumed/cancelled)}
\end{cases}
$$

### 2.2 Ask-Side Order Flow $e_a(t)$

Similarly for the ask side:

$$
e_a(t) = \begin{cases}
-q_a(t), & \text{if } P_a(t) < P_a(t-1) \quad \text{(Price decreased: aggressive sell pressure pushed ask down)} \\
q_a(t-1) - q_a(t), & \text{if } P_a(t) = P_a(t-1) \quad \text{(Price unchanged: net reduction in ask size)} \\
q_a(t-1), & \text{if } P_a(t) > P_a(t-1) \quad \text{(Price increased: previous best ask lifted or cancelled)}
\end{cases}
$$

### 2.3 Level-1 Order Flow Imbalance (L1-OFI)

The net Order Flow Imbalance at time $t$ is the sum of the signed bid and ask components:

$$
\text{OFI}_1(t) = e_b(t) + e_a(t)
$$

A positive $\text{OFI}_1(t) > 0$ indicates net buy-side pressure (buyer liquidity added, or seller liquidity consumed/cancelled). A negative $\text{OFI}_1(t) < 0$ indicates net sell-side pressure.

---

## 3. The Price Impact Equation

Cont et al. (2014) demonstrated that over short horizons $\Delta t$, the contemporaneous mid-price change $\Delta P_t = P_{mid}(t + \Delta t) - P_{mid}(t)$ exhibits a strong linear relationship with cumulative OFI:

$$
\Delta P_t = \beta \cdot \text{OFI}(t) + \epsilon_t
$$

Where:
- $\beta \approx \frac{1}{D}$ is the price impact coefficient, inversely proportional to the average market depth $D$.
- In high-liquidity instruments (e.g. BTCUSDT, EURUSD), $\beta$ is small (deep market, high capacity to absorb flow).
- In thin liquidity regimes, $\beta$ expands (orders move prices significantly).

---

## 4. Multi-Level OFI (M-OFI) Extension

While Level-1 OFI captures activity at the best quotes (NBBO), institutional market makers and algorithmic execution engines frequently place and cancel orders at deeper levels (e.g. L2 to L5).

For level $k \in \{1, 2, \dots, K\}$:

$$
e_b^{(k)}(t) = \begin{cases}
q_b^{(k)}(t), & \text{if } P_b^{(k)}(t) > P_b^{(k)}(t-1) \\
q_b^{(k)}(t) - q_b^{(k)}(t-1), & \text{if } P_b^{(k)}(t) = P_b^{(k)}(t-1) \\
-q_b^{(k)}(t-1), & \text{if } P_b^{(k)}(t) < P_b^{(k)}(t-1)
\end{cases}
$$

$$
e_a^{(k)}(t) = \begin{cases}
-q_a^{(k)}(t), & \text{if } P_a^{(k)}(t) < P_a^{(k)}(t-1) \\
q_a^{(k-1)}(t-1) - q_a^{(k)}(t), & \text{if } P_a^{(k)}(t) = P_a^{(k)}(t-1) \\
q_a^{(k)}(t-1), & \text{if } P_a^{(k)}(t) > P_a^{(k)}(t-1)
\end{cases}
$$

### Integrated Multi-Level OFI

An integrated OFI vector can be weighted across levels using a decaying harmonic or exponential weight $w_k$:

$$
\text{Integrated OFI}(t) = \sum_{k=1}^K w_k \cdot \left( e_b^{(k)}(t) + e_a^{(k)}(t) \right), \quad \text{where } \sum_{k=1}^K w_k = 1
$$

Default weight vector: $w_k = \frac{1/k}{\sum_{j=1}^K 1/j}$.

---

## 5. Microstructure Concept Comparison

| Metric | Definition | Data Requirement | Notes |
|---|---|---|---|
| **Trade Delta** | Signed executed trade volume ($V_{\text{buy}} - V_{\text{sell}}$) | Trades + Maker/Taker flag | Excludes resting limit adds and cancels |
| **CVD** | Cumulative Volume Delta ($\sum \text{Delta}$) | Trade ticks | Path-dependent; sensitive to reset point |
| **Order Book Imbalance (OBI)** | Static ratio: $\frac{Q_b - Q_a}{Q_b + Q_a}$ | L1 or L2 snapshot | Snapshot in time; does not capture order cancellations |
| **Microprice** | Depth-weighted price: $\frac{P_a Q_b + P_b Q_a}{Q_b + Q_a}$ | L1 snapshot | Sub-tick fair price indicator |
| **Level-1 OFI** | Dynamic flow entering/leaving top of book | Sequence L2 or MBO | Rigorous academic measure of order book events |
| **Multi-Level OFI** | Dynamic flow across top $K$ levels | Incremental L2 | Captures book replenishment and spoofing |

---

## 6. Academic References

1. **Cont, R., Kukanov, A., & Stoikov, S. (2014)**. *The Price Impact of Order Book Events*. Journal of Financial Econometrics, 12(1), 47–88. [arXiv:1011.6402](https://arxiv.org/abs/1011.6402)
2. **Gould, M. D., Porter, M. A., Williams, S., McDonald, M., Fenn, D. J., & Howison, S. D. (2013)**. *Limit order books*. Quantitative Finance, 13(11), 1709–1742. [arXiv:1012.0349](https://arxiv.org/abs/1012.0349)
3. **Gould, M. D., & Bonart, J. (2016)**. *Queue imbalance as a one-tick-ahead price predictor*. Market Microstructure and Liquidity, 2(02), 1650006. [arXiv:1512.03492](https://arxiv.org/abs/1512.03492)
4. **Xu, K., Lu, C., & Chen, J. (2020)**. *Multi-Level Order Flow Imbalance and Price Impact in Equity and Futures Markets*.
