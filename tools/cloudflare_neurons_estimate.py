"""Compute the Cloudflare Workers AI Neuron estimate before any inference run.

Run: python cloudflare_neurons_estimate.py
Rates are the official per-million-token Neuron rates published on the
Workers AI pricing page (fetched 2026-10-25).
"""

RATES = {
    # model: (input neurons / 1M tokens, output neurons / 1M tokens)
    "Granite 4.0 H Micro": (1542, 10158),
    "Llama 3.2 1B": (2457, 18252),
    "Llama 3.2 3B": (4625, 30475),
    "Qwen3 30B A3B": (4625, 30475),
    "Llama 3.1 8B FP8": (13778, 26128),
    "Llama 3.2 11B Vision": (4410, 61493),
}

# Measured on the NIM pilot: 3,104-3,122 prompt tokens per case, 40-197 completion.
IN_TOKENS = 3200
FREE_TIER = 10_000
USD_PER_1K = 0.011


def per_case(rate, out_tokens):
    rin, rout = rate
    return (IN_TOKENS / 1_000_000) * rin + (out_tokens / 1_000_000) * rout


def main():
    print(f"Assumptions: {IN_TOKENS} input tokens/case, temperature 0, max_tokens 2000")
    print(f"Free tier: {FREE_TIER:,} Neurons/day; overage ${USD_PER_1K}/1K\n")

    for out_tokens in (200, 500, 2000):
        print(f"=== completion budget {out_tokens} tokens (worst case) ===")
        for name, rate in RATES.items():
            n = per_case(rate, out_tokens)
            print(
                f"{name:24s} per-case {n:6.1f}  "
                f"5-case {n*5:7.0f} ({n*5/FREE_TIER*100:5.2f}%)  "
                f"17-holdout {n*17:7.0f} ({n*17/FREE_TIER*100:5.2f}%)  "
                f"54-dev {n*54:8.0f} ({n*54/FREE_TIER*100:6.2f}%)  "
                f"dev ${n*54*USD_PER_1K/1000:.4f}"
            )
        print()

    print("=== all six models, full dev (54 cases) ===")
    for out_tokens in (200, 2000):
        total = sum(per_case(r, out_tokens) * 54 for r in RATES.values())
        print(
            f"out={out_tokens:4d}: {total:8.0f} Neurons "
            f"({total/FREE_TIER*100:.1f}% of daily free tier), ${total*USD_PER_1K/1000:.4f}"
        )

    print("\n=== recommended gated sequence ===")
    cheapest = per_case(RATES["Llama 3.2 3B"], 200)
    print(f"1 probe (Llama 3.2 3B, 1 case)      ~{cheapest:.1f} Neurons ({cheapest/FREE_TIER*100:.3f}%)")
    print(f"5-case pilot (Llama 3.2 3B)         ~{cheapest*5:.0f} Neurons ({cheapest*5/FREE_TIER*100:.3f}%)")
    print(f"full dev (Llama 3.2 3B)             ~{cheapest*54:.0f} Neurons ({cheapest*54/FREE_TIER*100:.2f}%)")
    print(f"full dev, all 6 models              ~{sum(per_case(r,200)*54 for r in RATES.values()):.0f} Neurons "
          f"({sum(per_case(r,200)*54 for r in RATES.values())/FREE_TIER*100:.1f}%)")


if __name__ == "__main__":
    main()
